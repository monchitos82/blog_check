import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiohttp
from async_scrape import get_urls, BASE_URL


@pytest.mark.asyncio
async def test_get_urls_happy_path(tmp_path):
    with patch("async_scrape.BASE_PATH", str(tmp_path)):
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.status = 200
        mock_response.read = AsyncMock(
            return_value=b'<html><body><a href="https://monchitos82.github.io/blog/sub/page.html">Subpage</a></body></html>'
        )

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_response
        mock_session.get.return_value = cm

        existing = set()
        await get_urls(mock_session, existing, BASE_URL)

        assert BASE_URL in existing
        assert "https://monchitos82.github.io/blog/sub/page.html" in existing

        # Verify file creation
        assert (tmp_path / "index.html").exists()


@pytest.mark.asyncio
async def test_get_urls_non_ok_response(tmp_path):
    with patch("async_scrape.BASE_PATH", str(tmp_path)):
        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 404

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.return_value = mock_response
        mock_session.get.return_value = cm

        existing = set()
        await get_urls(mock_session, existing, BASE_URL)

        assert BASE_URL in existing
        # Should not create file or recurse on 404
        assert not (tmp_path / "index.html").exists()


@pytest.mark.asyncio
async def test_get_urls_network_timeout(tmp_path):
    with patch("async_scrape.BASE_PATH", str(tmp_path)):
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        cm = AsyncMock()
        cm.__aenter__.side_effect = asyncio.TimeoutError
        mock_session.get.return_value = cm

        existing = set()
        await get_urls(mock_session, existing, BASE_URL)

        assert BASE_URL in existing
        assert not (tmp_path / "index.html").exists()
