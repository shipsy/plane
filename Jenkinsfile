@Library('jenkins-library@master') _

// define vault configuration
def configuration = [
    engineVersion: 2, 
    timeout: 60,
    vaultCredentialId: 'jenkins-app-role', 
    vaultUrl: 'https://vault.secrets.shipsy.in'
]

// Project Level Configurations
def repository = "plane"
def projectEnv = "prod"

// Config Based configurations
def vaultConfigFilesMap = [
    "CONFIG" : "config.json",
]
def configStoragePath = "config-files"

// Validation Level Configurations
List<String> configFilesList = []
vaultConfigFilesMap.each { envVariable, configFileName ->
    configFilesList.add("${configStoragePath}/${configFileName}")
}

// Docker Based Configurations
def awsRegion = "eu-north-1"
def dockerBuildLevelArguments = [
    ENV_FILE_PATH: "${configStoragePath}/.env"
]

// Tags are "prod-<sha><cfgver>" (generateDockerImageName) — unique per build so
// updateTaskDefinition always registers a new revision.
def credentialsId = "ext_jenkins_login_user_vault"
def webImageNamePrefix   = "prod-plane-frontend"
def adminImageNamePrefix = "prod-plane-adminpanel"
def apiImageNamePrefix   = "prod-plane-apiserver"
def webImageName
def adminImageName
def apiImageName

// ECS Based Configurations
def clusterName = "logistics-applications-cluster"

// def mainServiceName = "demo-n8n"
// def workerServiceName = "demo-n8n-worker"
// def webhookServiceName = "demo-n8n-webhook"
def apiServiceName = "prod-plane-apiserver"
def celeryServiceName  = "prod-plane-celery"
def cbeatServiceName  = "prod-plane-celery-beat"
def frontEndServiceName  = "prod-plane-frontend"
def adminPanelServiceName  = "prod-plane-admin-panel"

def apiTaskDefinitionName    = "prod-plane-apiserver"
def celeryTaskDefinitionName = "prod-plane-apiserver-celery"
def cbeatTaskDefinitionName  = "prod-plane-apiserver-celery-beat"
def webTaskDefinitionName    = "prod-plane-frontend"
def adminTaskDefinitionName  = "prod-plane-admin-panel"

def apiCurrentTaskRevision
def celeryCurrentTaskRevision
def cbeatCurrentTaskRevision
def webCurrentTaskRevision
def adminCurrentTaskRevision

pipeline {
    agent any

    stages {
        // stage ("Send Build started message") {
        //     steps{
        //         sendSlackMessage (
        //             messageType: "start",
        //             slackEnvironment: "demo"
        //         )
        //     }
        // }

        stage ("Generate configs from vault") {
            steps {
                // define vault secret path and env var
                script {
                    def secret = [
                        [
                        path: "${repository}/${projectEnv}", 
                        secretValues: [
                                [envVar: 'CONFIG', vaultKey: 'config.json']
                            ]
                        ]
                    ]
                    // sh "echo ${secret}"
                    withVault(configuration: configuration, vaultSecrets: secret) {
                        sh """
                            set +x
                            echo "Vault CONFIG: \${CONFIG}"   # Debugging, remove in production
                            pwd
                            mkdir -p apiserver/${configStoragePath}
                            echo "\${CONFIG}" > apiserver/${configStoragePath}/.env
                        """

                        // Debugging: Show the contents of the .env file (optional for development only)
                        sh "cat apiserver/${configStoragePath}/.env"

                        // Verify the file has been created
                        sh "ls -l apiserver/${configStoragePath}/.env"
                    }
                }
            }
        }
        stage ("Create Docker Image Names") {
            steps {
                script {
                    webImageName = generateDockerImageName (
                        credentialsId : credentialsId,
                        dockerImageNamePrefix : webImageNamePrefix,
                        repository : repository,
                        projectEnv : projectEnv
                    ).toString()
                    // One checkout + one vault config for all three images,
                    // so reuse the web image's tag instead of three vault logins.
                    def uniqueTag = webImageName.split(':')[1]
                    adminImageName = "${adminImageNamePrefix}:${uniqueTag}".toString()
                    apiImageName   = "${apiImageNamePrefix}:${uniqueTag}".toString()
                }
            }
        }

        stage ("Build docker image") {
            parallel {
                stage ("Build Web Image") {
                    steps {
                        buildDockerImage (
                            awsRegion : awsRegion,
                            imageName : webImageName,
                            directoryPath : ".",
                            dockerfilePath : "web/Dockerfile.web"
                        )
                    }
                }
                stage ("Build Admin Image") {
                    steps {
                        buildDockerImage (
                            awsRegion : awsRegion,
                            imageName : adminImageName,
                            directoryPath : ".",
                            dockerfilePath : "admin/Dockerfile.admin"
                        )
                    }
                }
                stage ("Build API Image") {
                    steps {
                        buildDockerImage (
                            awsRegion : awsRegion,
                            dockerBuildArgs : dockerBuildLevelArguments,
                            imageName : apiImageName,
                            directoryPath : "apiserver",
                            dockerfilePath : "apiserver/Dockerfile.api"
                        )
                    }
                }
            }
        }

        stage("Push to registry") {
            parallel {
                stage ("Push Web Image") {
                    steps {
                        pushDockerImage (
                            awsRegion : awsRegion,
                            imageName : webImageName
                        )
                    }
                }
                stage ("Push Admin Image") {
                    steps {
                        pushDockerImage (
                            awsRegion : awsRegion,
                            imageName : adminImageName
                        )
                    }
                }
                stage ("Push API Image") {
                    steps {
                        pushDockerImage (
                            awsRegion : awsRegion,
                            imageName : apiImageName
                        )
                    }
                }
            }
        }

        stage("Deploy Plane") {
            parallel {
                stage("Deploy Frontend") {
                    steps {
                        script {
                            webCurrentTaskRevision = updateTaskDefinition (
                                taskDefinitionName : webTaskDefinitionName,
                                dockerImageName : webImageName,
                                awsRegion : awsRegion
                            )
                            updateServiceOnECS (
                                ecsClusterName : clusterName,
                                ecsServiceName : frontEndServiceName,
                                taskDefinitionName : webTaskDefinitionName,
                                currentTaskRevision : webCurrentTaskRevision,
                                awsRegion : awsRegion
                            )
                        }
                    }
                }

                stage("Deploy Admin") {
                    steps {
                        script {
                            adminCurrentTaskRevision = updateTaskDefinition (
                                taskDefinitionName : adminTaskDefinitionName,
                                dockerImageName : adminImageName,
                                awsRegion : awsRegion
                            )
                            updateServiceOnECS (
                                ecsClusterName : clusterName,
                                ecsServiceName : adminPanelServiceName,
                                taskDefinitionName : adminTaskDefinitionName,
                                currentTaskRevision : adminCurrentTaskRevision,
                                awsRegion : awsRegion
                            )
                        }
                    }
                }

                stage("Deploy API") {
                    steps {
                        script {
                            apiCurrentTaskRevision = updateTaskDefinition (
                                taskDefinitionName : apiTaskDefinitionName,
                                dockerImageName : apiImageName,
                                awsRegion : awsRegion
                            )
                            updateServiceOnECS (
                                ecsClusterName : clusterName,
                                ecsServiceName : apiServiceName,
                                taskDefinitionName : apiTaskDefinitionName,
                                currentTaskRevision : apiCurrentTaskRevision,
                                awsRegion : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy Celery") {
                    steps {
                        script {
                            celeryCurrentTaskRevision = updateTaskDefinition (
                                taskDefinitionName : celeryTaskDefinitionName,
                                dockerImageName : apiImageName,
                                awsRegion : awsRegion
                            )
                            updateServiceOnECS (
                                ecsClusterName : clusterName,
                                ecsServiceName : celeryServiceName,
                                taskDefinitionName : celeryTaskDefinitionName,
                                currentTaskRevision : celeryCurrentTaskRevision,
                                awsRegion : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy Beat") {
                    steps {
                        script {
                            cbeatCurrentTaskRevision = updateTaskDefinition (
                                taskDefinitionName : cbeatTaskDefinitionName,
                                dockerImageName : apiImageName,
                                awsRegion : awsRegion
                            )
                            updateServiceOnECS (
                                ecsClusterName : clusterName,
                                ecsServiceName : cbeatServiceName,
                                taskDefinitionName : cbeatTaskDefinitionName,
                                currentTaskRevision : cbeatCurrentTaskRevision,
                                awsRegion : awsRegion
                            )
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            sendSlackMessage (
                messageType: "post",
                slackEnvironment: "prod"
            )
        }
    }
}