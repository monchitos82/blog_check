import asyncio
import logging
import os
import aiohttp
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("crawler")

BASE_URL = "https://monchitos82.github.io/blog"
BASE_PATH = "./content"

async def get_urls(session: aiohttp.ClientSession, existing: set[str], url: str = BASE_URL) -> None:
    if url in existing:
        return
    existing.add(url)
    log.info(f"Crawling URL: {url}")

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if not response.ok:
                log.warning(f"Failed to fetch {url}, status code: {response.status}")
                return
            content = await response.read()
    except asyncio.TimeoutError:
        log.error(f"Timeout while fetching URL: {url}")
        return
    except Exception as error:
        log.error(f"Network error while fetching {url}: {error}")
        return

    try:
        split_url = url.replace(BASE_URL, "").split("/")
        url_path = "/".join(split_url[1:-1])
        url_file = split_url[-1]
        if len(url_file.split(".")) < 2:
            url_path = "/".join(split_url[1:])
            url_file = "index.html"

        local_dir = os.path.join(BASE_PATH, url_path)
        local_file = os.path.join(local_dir, url_file)
        os.makedirs(local_dir, exist_ok=True)

        with open(local_file, "wb") as f:
            f.write(content)
        log.info(f"Successfully saved {url} to {local_file}")

        if url_file.endswith("html") or not url_file:
            soup = BeautifulSoup(content, "html.parser")
            url_anchors = soup.find_all("a", href=True)
            url_anchors.extend(soup.find_all("link", href=True))
            url_anchors.extend(soup.find_all("img", src=True))

            tasks = []
            for anchor in url_anchors:
                anchor_url = anchor.get("href") or anchor.get("src")
                if anchor_url and anchor_url.startswith(BASE_URL) and anchor_url not in existing:
                    tasks.append(
                        get_urls(session=session, existing=existing, url=anchor_url)
                    )
            if tasks:
                await asyncio.gather(*tasks)

    except OSError as error:
        log.error(f"File system error processing {url}: {error}")
    except Exception as error:
        log.error(f"Parsing error for {url}: {error}")


async def main() -> None:
    content_url = f"{BASE_URL}/content.md"
    existing = set()
    async with aiohttp.ClientSession() as session:
        await get_urls(session=session, existing=existing, url=BASE_URL)
        await get_urls(session=session, existing=existing, url=content_url)


if __name__ == "__main__":
    asyncio.run(main())
