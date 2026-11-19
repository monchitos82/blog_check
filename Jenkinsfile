pipeline {
    agent { label 'python' }
    environment {
        // site specifics
        AUTHOR = "Monchitos82"
        ACCOUNT = "monchitos82"

        // build specifics
        SOURCE = "blog"
        GIT_URL = "ssh://git@host.containers.internal:2222/jenkins/blog.git"

        // Base URL definitions
        BASE_URL = "https://${ACCOUNT}.github.io"
        LOCAL_BASE_URL = "http://127.0.0.1:2080/site/blog"

        // Local copy definitions
        LOCAL_PATH_ROOT = "/opt/deploy"
        LOCAL_PATH_SITE = "${LOCAL_PATH_ROOT}/site/blog"

    }
    stages {
        stage('Environment Setup') {
            steps {
                script {
                    if (!fileExists('/home/jenkins/.local/bin/uv')) {
                        sh '''
                            curl -LsSf https://astral.sh/uv/install.sh | sh
                            export PATH="$HOME/.local/bin:$PATH"
                            uv sync --frozen
                        '''
                    }
                }
            }
        }
        stage('Sources Setup') {
            steps {
                script {
                    if (params.CLEAN_REPOSITORIES) {
                        dir("../${SOURCE}") { deleteDir() }
                        sh '''
                            cd ..
                            git clone ${GIT_URL}
                        '''
                    } else {
                        if (fileExists("/home/jenkins/agent/workspace/${SOURCE}")) {
                            sh '''
                            echo "Source is already present"
                            cd ..
                            cd ${SOURCE}
                            git pull
                            cd ../blog_check
                            '''
                        } else {
                            sh '''
                            cd ..
                            git clone ${GIT_URL}
                            '''
                        }
                    }
                }
            }
        }

        stage('Clone from blog') {
            steps {
                script {
                    sh '''
                    mkdir -p content
                    $HOME/.local/bin/uv run async_scrape.py
                    '''
                }
            }

        }
        stage('Local Publish') {
            steps {
                sh '''
                mkdir -p ${LOCAL_PATH_SITE}
                cp -r content/* ${LOCAL_PATH_SITE}
                find ${LOCAL_PATH_SITE} -type f -exec sed -i "s|${BASE_URL}|${LOCAL_BASE_URL}|g" {} +
                '''
            }
        }
        stage('LLM Review Content') {
            steps {
                sh '''
                echo "---" > ${LOCAL_PATH_SITE}/llm_summary.md
                echo "## ${filename} ##" >> ${LOCAL_PATH_SITE}/llm_summary.md
                PYTHONPATH=/home/jenkins/agent/workspace/blog_check
                pwd
                $HOME/.local/bin/uv run llm_check.py content/content.md >> ${LOCAL_PATH_SITE}/llm_summary.md
                echo "" >> ${LOCAL_PATH_SITE}/llm_summary.md
                '''
            }
        }
    }
    post {
        failure {
            echo 'Upon failure you should clean repositories for the next run!'
            cleanWs()
        }
        cleanup {
            script {
                if (params.CLEAN_REPOSITORIES) {
                    dir("../${SOURCE}") { deleteDir() }
                    dir("./content") { deleteDir() }
                }
            }
        }
    }
}
