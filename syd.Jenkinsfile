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
def awsRegion = "ap-southeast-2"
def dockerBuildLevelArguments = [
    ENV_FILE_PATH: "${configStoragePath}/.env"
]

// Image names = syd ECR repo names (one image per repo).
// The apiserver code image is pushed to 3 repos (apiserver, celery, beat)
// because on syd each of those services deploys from its own repo.
// Tags are "prod-<sha><cfgver>" (generateDockerImageName) — unique per build so
// updateTaskDefinition always registers a new revision.
def credentialsId = "ext_jenkins_login_user_vault"
def webImageNamePrefix    = "prod-plane-frontend-syd-ecr"
def adminImageNamePrefix  = "prod-plane-admin-panel-syd-ecr"
def apiImageNamePrefix    = "prod-plane-apiserver-syd-ecr"
def celeryImageNamePrefix = "plane-apiserver-celery-syd-ecr"
def beatImageNamePrefix   = "prod-plane-celery-beat-syd-ecr"
def webImageName
def adminImageName
def apiImageName
def celeryImageName
def beatImageName

// ECS Based Configurations
def clusterName = "logistics-applications-cluster-syd"

def apiServiceName        = "prod-plane-apiserver-syd-service"
def celeryServiceName     = "plane-apiserver-celery-syd-service"
def cbeatServiceName      = "prod-plane-celery-beat-syd-service"
def frontEndServiceName   = "prod-plane-frontend-syd-service"
def adminPanelServiceName = "prod-plane-admin-panel-syd-service"

def apiTaskDefinitionName    = "prod-plane-apiserver-syd-td"
def celeryTaskDefinitionName = "plane-apiserver-celery-syd-td"
def cbeatTaskDefinitionName  = "prod-plane-celery-beat-syd-td"
def webTaskDefinitionName    = "prod-plane-frontend-syd-td"
def adminTaskDefinitionName  = "prod-plane-admin-panel-syd-td"

def apiCurrentTaskRevision
def celeryCurrentTaskRevision
def cbeatCurrentTaskRevision
def webCurrentTaskRevision
def adminCurrentTaskRevision

pipeline {
    agent { label 'jenkins-sydney-node' }

    stages {
        stage ("Generate configs from vault") {
            steps {
                // define vault secret path and env var
                script {
                    def secret = [
                        [
                        path: "${repository}/${projectEnv}",
                        secretValues: [
                                [envVar: 'CONFIG', vaultKey: 'config.syd.json']
                            ]
                        ]
                    ]
                    withVault(configuration: configuration, vaultSecrets: secret) {
                        sh """
                            set +x
                            mkdir -p apiserver/${configStoragePath}
                            echo "\${CONFIG}" > apiserver/${configStoragePath}/.env
                        """
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
                    // All five images share one code checkout + one vault config,
                    // so reuse the web image's tag instead of five vault logins.
                    def uniqueTag = webImageName.split(':')[1]
                    adminImageName  = "${adminImageNamePrefix}:${uniqueTag}".toString()
                    apiImageName    = "${apiImageNamePrefix}:${uniqueTag}".toString()
                    celeryImageName = "${celeryImageNamePrefix}:${uniqueTag}".toString()
                    beatImageName   = "${beatImageNamePrefix}:${uniqueTag}".toString()
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

        // Tag the apiserver image into the celery + beat repos
        // (same code image, separate syd ECR repos per service).
        stage ("Tag API image for celery + beat") {
            steps {
                script {
                    def ecrHost = "989674740158.dkr.ecr.${awsRegion}.amazonaws.com"
                    sh """
                        set +x
                        aws ecr get-login-password --region ${awsRegion} | docker login --username AWS --password-stdin ${ecrHost}
                        docker tag ${ecrHost}/${apiImageName} ${ecrHost}/${celeryImageName}
                        docker tag ${ecrHost}/${apiImageName} ${ecrHost}/${beatImageName}
                    """
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
                stage ("Push Celery Image") {
                    steps {
                        pushDockerImage (
                            awsRegion : awsRegion,
                            imageName : celeryImageName
                        )
                    }
                }
                stage ("Push Beat Image") {
                    steps {
                        pushDockerImage (
                            awsRegion : awsRegion,
                            imageName : beatImageName
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
                                dockerImageName : celeryImageName,
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
                                dockerImageName : beatImageName,
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
