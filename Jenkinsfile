pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 5, unit: 'MINUTES')
    }

    triggers {
        cron('TZ=Europe/Moscow\n0 6,12,18 * * *')
    }

    stages {
        stage('Watch tests') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'jenkins_watchdog_api',
                        usernameVariable: 'JENKINS_API_USER',
                        passwordVariable: 'JENKINS_API_TOKEN'
                    ),
                    string(credentialsId: 'telegram_proxy_url', variable: 'TELEGRAM_PROXY_URL'),
                    string(credentialsId: 'telegram_proxy_auth_secret', variable: 'TELEGRAM_PROXY_AUTH_SECRET'),
                    string(credentialsId: 'telegram_proxy_global_test', variable: 'TELEGRAM_PROXY_CREDS')
                ]) {
                    sh '''
                        set -eu
                        python3 watchdog.py --targets targets.json
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Watchdog check completed.'
            cleanWs()
        }
    }
}
