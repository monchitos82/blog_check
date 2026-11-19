# Blog Check

This project circles around the Jenkins workflow defined in the `Jenkinsfile`. This will trigger a scrapping job from the repository, deploy a local blog and validate its contents using an LLM through ollama.

Things you will need for this to work (I use them through podman, but you may choose your own flavor):

  - Github (for the blog source)
  - Nginx (for the local deployment)
  - Jenkins + Jenkins Python agent (you can get an idea on how to build these from my terraform plans)
  - Python (because ^)
  - Ollama (If you want the LLM local check)
  - OTEL (If you want to read through the process, this is 100% **optional**)


