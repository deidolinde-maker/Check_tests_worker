pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 5, unit: 'MINUTES')
    }

    triggers {
        cron('''
TZ=Europe/Moscow
H/10 * * * *
''')
    }

    stages {
        stage('Watch tests') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: 'jenkins_watchdog_api',
                        usernameVariable: 'JENKINS_API_USER',
                        passwordVariable: 'JENKINS_API_TOKEN'
                    )
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
