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
def webImageName    = "prod-plane-frontend-syd-ecr:latest"
def adminImageName  = "prod-plane-admin-panel-syd-ecr:latest"
def apiImageName    = "prod-plane-apiserver-syd-ecr:latest"
def celeryImageName = "plane-apiserver-celery-syd-ecr:latest"
def beatImageName   = "prod-plane-celery-beat-syd-ecr:latest"

// ECS Based Configurations
def clusterName = "logistics-applications-cluster-syd"

def apiServiceName        = "prod-plane-apiserver-syd-service"
def celeryServiceName     = "plane-apiserver-celery-syd-service"
def cbeatServiceName      = "prod-plane-celery-beat-syd-service"
def frontEndServiceName   = "prod-plane-frontend-syd-service"
def adminPanelServiceName = "prod-plane-admin-panel-syd-service"

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
                            deployServiceOnECS (
                                awsRegion : awsRegion,
                                imageName : webImageName,
                                ecsClusterName : clusterName,
                                ecsServiceName : frontEndServiceName,
                                timeout : 300
                            )
                        }
                    }
                }

                stage("Deploy Admin") {
                    steps {
                        script {
                            deployServiceOnECS (
                                awsRegion : awsRegion,
                                imageName : adminImageName,
                                ecsClusterName : clusterName,
                                ecsServiceName : adminPanelServiceName,
                                timeout : 300
                            )
                        }
                    }
                }

                stage("Deploy API") {
                    steps {
                        script {
                            deployServiceOnECS (
                                awsRegion : awsRegion,
                                imageName : apiImageName,
                                ecsClusterName : clusterName,
                                ecsServiceName : apiServiceName,
                                timeout : 300
                            )
                        }
                    }
                }
                stage("Deploy Celery") {
                    steps {
                        script {
                            deployServiceOnECS (
                                awsRegion : awsRegion,
                                imageName : celeryImageName,
                                ecsClusterName : clusterName,
                                ecsServiceName : celeryServiceName,
                                timeout : 300
                            )
                        }
                    }
                }
                stage("Deploy Beat") {
                    steps {
                        script {
                            deployServiceOnECS (
                                awsRegion : awsRegion,
                                imageName : beatImageName,
                                ecsClusterName : clusterName,
                                ecsServiceName : cbeatServiceName,
                                timeout : 300
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
