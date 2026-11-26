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
    // Pinned to the controller: `agent any` can land on jenkins-oregon-node, which has
    // no [default] AWS profile, so jenkins-library's `aws ecr get-login-password
    // --profile default` fails ("password is empty"). The controller has the profile
    // (api-gateway's EU/Sydney jobs build there fine). Revert to `agent any` once the
    // Oregon node has AWS credentials.
    agent { label 'master' }   // pre-2.307 Jenkins: the controller's label is 'master', not 'built-in'

    stages {
        stage("Send Build started message") {
            steps { sendSlackMessage(messageType: "start", slackEnvironment: projectEnv) }
        }

        stage("Create Docker Image Names") {
            steps {
                script {
                    // generateDockerImageName returns "<prefix>:prod-<sha><cfgver>". One checkout and
                    // one Vault config feed all three images, so reuse the web tag instead of three
                    // Vault logins. .toString() on purpose: these are read in later stages and get
                    // CPS-serialized, so keep plain Strings, not GStrings.
                    webImageName = generateDockerImageName(
                        credentialsId        : credentialsId,
                        dockerImageNamePrefix: webImageNamePrefix,
                        repository           : repository,
                        projectEnv           : projectEnv
                    ).toString()
                    def uniqueTag = webImageName.split(':')[1]
                    adminImageName = "${adminImageNamePrefix}:${uniqueTag}".toString()
                    apiImageName   = "${apiImageNamePrefix}:${uniqueTag}".toString()
                    echo "Images: ${webImageName}, ${adminImageName}, ${apiImageName}"
                }
            }
        }

        stage("Generate configs from vault") {
            steps {
                script {
                    def configFile = "apiserver/${configStoragePath}/.env"
                    def secret = [[
                        path        : "${repository}/${projectEnv}",
                        secretValues: [[envVar: 'CONFIG', vaultKey: 'config.json']]
                    ]]
                    withVault(configuration: configuration, vaultSecrets: secret) {
                        // Never echo/cat the config: it holds prod secrets and lands in the build log.
                        // Check the VALUE, not the file: `echo` of an empty variable still writes a
                        // newline, so a non-empty-file test passes and we'd ship a config-less image.
                        sh """
                            set +x
                            mkdir -p \$(dirname ${configFile})
                            if [ -z "\${CONFIG}" ]; then
                              echo "FATAL: required Vault key 'config.json' missing or empty at '${repository}/${projectEnv}'" >&2
                              exit 1
                            fi
                            printf '%s\\n' "\${CONFIG}" > ${configFile}
                        """
                    }
                }
            }
        }

        // Build and push run sequentially, not in parallel: three concurrent
        // `aws ecr get-login-password | docker login` calls on one agent race on
        // ~/.docker/config.json and interleave their logs, which hid the real error.
        stage("Build Web image") {
            steps {
                buildDockerImage(
                    awsRegion     : awsRegion,
                    imageName     : webImageName,
                    directoryPath : ".",
                    dockerfilePath: "web/Dockerfile.web"
                )
            }
        }

        stage("Build Admin image") {
            steps {
                buildDockerImage(
                    awsRegion     : awsRegion,
                    imageName     : adminImageName,
                    directoryPath : ".",
                    dockerfilePath: "admin/Dockerfile.admin"
                )
            }
        }

        stage("Build API image") {
            steps {
                buildDockerImage(
                    awsRegion      : awsRegion,
                    imageName      : apiImageName,
                    directoryPath  : "apiserver",
                    dockerfilePath : "apiserver/Dockerfile.api",
                    dockerBuildArgs: dockerBuildLevelArguments
                )
            }
        }

        stage("Push images to registry") {
            steps {
                pushDockerImage(awsRegion: awsRegion, imageName: webImageName)
                pushDockerImage(awsRegion: awsRegion, imageName: adminImageName)
                pushDockerImage(awsRegion: awsRegion, imageName: apiImageName)
            }
        }

        // Deploys stay parallel: they're independent ECS API calls (no docker login), and
        // celery/beat must roll out alongside the API image they share.
        stage("Deploy Plane") {
            parallel {
                stage("Deploy Frontend") {
                    steps {
                        script {
                            webCurrentTaskRevision = updateTaskDefinition(
                                taskDefinitionName: webTaskDefinitionName,
                                dockerImageName   : webImageName,
                                awsRegion         : awsRegion
                            )
                            updateServiceOnECS(
                                ecsClusterName     : clusterName,
                                ecsServiceName     : frontEndServiceName,
                                taskDefinitionName : webTaskDefinitionName,
                                currentTaskRevision: webCurrentTaskRevision,
                                awsRegion          : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy Admin") {
                    steps {
                        script {
                            adminCurrentTaskRevision = updateTaskDefinition(
                                taskDefinitionName: adminTaskDefinitionName,
                                dockerImageName   : adminImageName,
                                awsRegion         : awsRegion
                            )
                            updateServiceOnECS(
                                ecsClusterName     : clusterName,
                                ecsServiceName     : adminPanelServiceName,
                                taskDefinitionName : adminTaskDefinitionName,
                                currentTaskRevision: adminCurrentTaskRevision,
                                awsRegion          : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy API") {
                    steps {
                        script {
                            apiCurrentTaskRevision = updateTaskDefinition(
                                taskDefinitionName: apiTaskDefinitionName,
                                dockerImageName   : apiImageName,
                                awsRegion         : awsRegion
                            )
                            updateServiceOnECS(
                                ecsClusterName     : clusterName,
                                ecsServiceName     : apiServiceName,
                                taskDefinitionName : apiTaskDefinitionName,
                                currentTaskRevision: apiCurrentTaskRevision,
                                awsRegion          : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy Celery") {
                    steps {
                        script {
                            celeryCurrentTaskRevision = updateTaskDefinition(
                                taskDefinitionName: celeryTaskDefinitionName,
                                dockerImageName   : apiImageName,
                                awsRegion         : awsRegion
                            )
                            updateServiceOnECS(
                                ecsClusterName     : clusterName,
                                ecsServiceName     : celeryServiceName,
                                taskDefinitionName : celeryTaskDefinitionName,
                                currentTaskRevision: celeryCurrentTaskRevision,
                                awsRegion          : awsRegion
                            )
                        }
                    }
                }
                stage("Deploy Beat") {
                    steps {
                        script {
                            cbeatCurrentTaskRevision = updateTaskDefinition(
                                taskDefinitionName: cbeatTaskDefinitionName,
                                dockerImageName   : apiImageName,
                                awsRegion         : awsRegion
                            )
                            updateServiceOnECS(
                                ecsClusterName     : clusterName,
                                ecsServiceName     : cbeatServiceName,
                                taskDefinitionName : cbeatTaskDefinitionName,
                                currentTaskRevision: cbeatCurrentTaskRevision,
                                awsRegion          : awsRegion
                            )
                        }
                    }
                }
            }
        }
    }

    post {
        always { sendSlackMessage(messageType: "post", slackEnvironment: projectEnv) }
    }
}
