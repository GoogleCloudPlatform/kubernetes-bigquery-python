



Copyright (C) 2014 Google Inc.

# Real-time data analysis using Kubernetes, Redis, and BigQuery

- [Introduction](#introduction)
- [Prerequisites and initial setup](#prerequisites-and-initial-setup)
  - [Create and configure a Google Cloud Platform project](#create-and-configure-a-google-cloud-platform-project)
  - [Set up the Google Cloud SDK, or use your project's Cloud Shell](#set-up-the-google-cloud-sdk-or-use-your-projects-cloud-shell)
  - [Clone the example repo](#clone-the-example-repo)
  - [Create a BigQuery table](#create-a-bigquery-table)
  - [Create a Twitter application and access token](#create-a-twitter-application-and-access-token)
- [Start up a GKE cluster](#start-up-a-gke-cluster)
- [Configure and deploy your app](#configure-and-deploy-your-app)
  - [Kubernetes Pods, Replica Sets, Deployments, and Services](#kubernetes-pods-replica-sets-deployments-and-services)
  - [Deployment configuration](#deployment-configuration)
  - [Deploy your app](#deploy-your-app)
    - [Optional: resize the `bigquery-controller`](#optional-resize-the-bigquery-controller)
- [Query your BigQuery table](#query-your-bigquery-table)
- [Shut down your replicated pods and cluster](#shut-down-your-replicated-pods-and-cluster)
- [Troubleshooting](#troubleshooting)
- [Appendix: Optional: Use a customized Docker image for your app](#appendix-optional-use-a-customized-docker-image-for-your-app)


## Introduction

This directory contains an example [Google Kubernetes Engine](https://cloud.google.com/kubernetes-engine/) (GKE) app that shows how you can build a 'pipeline' to stream Twitter data into [BigQuery](https://cloud.google.com/bigquery/what-is-bigquery), via [Redis](http://redis.io/).

Kubernetes Engine is Google's managed version of [Kubernetes](http://github.com/GoogleCloudPlatform/kubernetes),
an open source container orchestrator originally developed by Google, and now managed by a community of contributors.
We won't go into much detail about Kubernetes' features in this tutorial, but see its [docs](https://kubernetes.io/docs/home/) for more information.

[Bigquery](https://cloud.google.com/bigquery/what-is-bigquery)  lets you run fast, SQL-like queries against multi-terabyte datasets in seconds, using the processing power of Google's infrastructure.

The app uses uses Redis to buffer the data coming in from Twitter and to decouple ingestion from processing.
One of the Kubernetes app *pods* reads the data from Twitter and dumps tweets into a Redis cache.  Other 
pods do blocking reads on the Redis cache. When tweet data is available, these pods grab data in small batches, and stream it into BigQuery.  The figure below suggests this flow.

<img src="https://cloud.google.com/solutions/real-time/images/kubernetes-bigquery-python-architecture.svg" width="680">

This app can be thought of as a 'workflow' type of app-- it doesn't have a web
front end (though Kubernetes is great for those types of apps as well).
Instead, it is designed to continously run a scalable data ingestion pipeline.

See also a related app, in the `../pubsub` directory of this repo, which uses [Google Cloud PubSub](https://cloud.google.com/pubsub/overview) instead of Redis. The general structure of this example is similar in many respects to that PubSub example. 

Note: This tutorial uses several **billable components** of Google Cloud
Platform. The cost of running this tutorial will vary depending on run time.
New Cloud Platform users may be eligible for a [free trial](/free-trial).

## Prerequisites and initial setup

### Create and configure a Google Cloud Platform project

To work through this example, you must have a Google Cloud Platform project with
the required APIs enabled. In the [Cloud Developers Console](https://console.developers.google.com),
create a new project or choose an existing project, then in the `APIs & auth > APIs` panel,
enable the BigQuery, Google Compute Engine, Google Cloud Storage, and Google Cloud Storage JSON APIs.
You will be prompted to enable billing if you have not previously done so.

### Set up the Google Cloud SDK, or use your project's Cloud Shell

This tutorial uses `gcloud`, the [Google Cloud SDK](https://cloud.google.com/sdk/), to interact with GKE and other parts of the Google Cloud Platform (GCP). If you like, you can run the rest of the tutorial from the [Cloud Shell](https://cloud.google.com/shell/docs/) of your GCP project.  It has everything installed that you will need, including `gcloud`.
Start up the Cloud Shell by clicking on this 'prompt' icon in the
[Cloud Console](https://console.developers.google.com):

<img src="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/Screenshot_2017-12-05_11_27_47.png" >

Alternately, you can install the SDK according to [these instructions](https://cloud.google.com/sdk/downloads), and run locally, e.g. on your laptop. If you install locally, make sure that you've authenticated using your Google Account:

```sh
gcloud auth login
```

then **set the default project** for the Cloud SDK to your project:

```sh
gcloud config set project <your_project_id>
```

In the Cloud Shell, you won't have to auth, but confirm you're using the correct project via:

```sh
gcloud config list project
```

and set it as above if necessary.

### Clone the example repo

If you haven't already, clone the Github repository for this example:

```sh
git clone https://github.com/GoogleCloudPlatform/kubernetes-bigquery-python.git
```

(If you prefer, you can
[download](https://github.com/GoogleCloudPlatform/kubernetes-bigquery-python/archive/master.zip) it instead.)

Then change to the `redis` subdirectory of the repo:

```sh
cd kubernetes-bigquery-python/redis
```

We'll stay in this directory for the rest of the tutorial.


### Create a BigQuery table

Next, create a BigQuery table to store your tweets. BigQuery groups
tables into abstraction layers called datasets, so first create a dataset as necessary.  You can do this from the [web UI](https://cloud.google.com/bigquery/docs/tables#create-table), or from the command line like this:

```sh
bq mk <your-dataset-name>
```

The `bq` command line tool is included in the Cloud SDK.

If you prefer, you can use an existing project dataset instead.

Then, create a new table (e.g., `tweets`) in that
dataset, to contain your incoming tweets. Each BigQuery table must be defined by
a schema. This example includes a predefined schema in the `kubernetes-bigquery-python/bigquery-setup` subdirectory,
`schema.json`, that you can use to define your table.  From the `redis` directory, run:

```sh
bq mk -t <your-dataset-name>.tweets ../bigquery-setup/schema.json
```

(If you prefer, you can also create your table via the web BigQuery UI, pasting in the schema from `schema.json`).

### Create a Twitter application and access token

To use the Twitter API, you need to create a Twitter application.

[Create a Twitter account](https://twitter.com/signup) as necessary, then
[create a Twitter application.](https://apps.twitter.com/).

In the Twitter Application Management page, navigate to the **Keys and
Access Tokens** tab.  Note your `Consumer Key` and `Consumer Secret`.

Then, click the **Create my access token** button to create a new access token, and note your
`Access Token` and `Access Token Secret`.


## Start up a GKE cluster

Create a new GKE cluster in the [Cloud Console](https://console.cloud.google.com/kubernetes/) by essentially following the instructions [here](https://cloud.google.com/kubernetes-engine/docs/how-to/creating-a-container-cluster), except that you will enable additional *scopes* for the cluster nodes before you click the "Create" button.

Click the "More" link towards the bottom of the GKE cluster creation page:

<a href="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create1.png" target="_blank"><img src="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create1.png" width=500/></a>

In the expanded panel, enable BigQuery project access:

<a href="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create2.png" target="_blank"><img src="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create2.png" width=500/></a>

You can optionally add PubSub project access, if you want to use this same cluster for the [PubSub](../pubsub) version of of this example (you won't need to access those APIs here, though):

<a href="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create3.png" target="_blank"><img src="https://storage.googleapis.com/amy-jo/images/k8s-twitter-pipeline/gke_create3.png" width=500/></a>

Click "Create" when you're done. This configuration will let apps running on this cluster access the BigQuery (and optionally PubSub) APIs.

**Notes**: It's possible to create a GKE cluster [from the command line](https://cloud.google.com/sdk/gcloud/reference/container/clusters/create) as well.   
If you've already run the [PubSub](../pubsub) tutorial, you can use the same cluster for this example.

Once your cluster is created, configure `kubectl` command-line access.  You can see the command that does this by clicking into the cluster details in the [Cloud Console](https://console.cloud.google.com/kubernetes/), then clicking the "Connect to cluster" link.  You'll be shown a command that looks like the following, but configured for your info.

```sh
gcloud container clusters get-credentials <cluster-name> --zone <cluster-zone> --project <your-project-name>
```

Run the version of that command for your cluster, then check that it was successful by running:

```sh
kubectl get nodes
```

## Configure and deploy your app

Now you're ready to configure your app.  This requires editing two Kubernetes `.yaml` config files.
(If you should want to do any customization of the app code, see the section: [Appendix: Use a customized Docker image for your app](#appendix-use-a-customized-docker-image-for-your-app). Build and push your container image before you deploy.)

### Kubernetes Pods, Replica Sets, Deployments, and Services

In Kubernetes, [pods](https://github.com/GoogleCloudPlatform/kubernetes/blob/master/docs/pods.md)-- rather than individual application containers-- are the smallest deployable units that can be created, scheduled, and managed.

A [replica set](http://kubernetes.io/docs/user-guide/replicasets/) ensures that a specified number of pod "replicas" are running at any one time. If there are too many, it will kill some. If there are too few, it will start more. As opposed to just creating singleton pods or even creating pods in bulk, a replica set replaces pods that are deleted or terminated for any reason, such as in the case of node failure.

A [Deployment](http://kubernetes.io/docs/user-guide/deployments/) provides declarative updates for Pods and Replica Sets. You only need to describe the desired state in a Deployment object, and the Deployment controller will change the actual state to the desired state at a controlled rate for you.

A [Service](https://kubernetes.io/docs/concepts/services-networking/connect-applications-service/) is an abstraction which defines a logical set of Pods running somewhere in your cluster, that all provide the same functionality. 

In this app, we'll use deployments for the different components of the app, and set up a Redis master behind a service, so that the other parts of the app know how to contact it.

`redis-master.yaml` starts up a Redis master, and `redis-master-service.yaml` sets up its service, using the `redis-master` label as its _selector_.  
Note: for this simple example, we're not setting up any kind of persistent backing mechanism for Redis.

`twitter-stream.yaml` defines one replica of a container that will read in tweets via the Twitter streaming API and dump them to a Redis cache. We're only using one replica here so that we don't open up multiple Twitter API connections on the same app.  However, we're still using a replicated pod for the robustness that gives us-- if the pod crashes for some reason, it will be restarted, since will specify that there should always be one running.

`bigquery-controller.yaml` defines two replicas of a pod that do  
blocking reads on the Redis cache. When tweet data is available, these pods grab data in small batches, and stream it into BigQuery. Here, we can use multiple pods. If source throughput were to increase, we could increase the number of these  `bigquery-controller` pods.

### Deployment configuration

Edit `twitter-stream.yaml`.
Set the Twitter authentication information to the values you noted when setting up your Twitter application
(`CONSUMERKEY`,`CONSUMERSECRET`, `ACCESSTOKEN`, and `ACCESSTOKENSEC`).

Edit `bigquery-controller.yaml`.  Set your `PROJECT_ID`, `BQ_DATASET`, and `BQ_TABLE` information.

(If you optionally built your own docker image as described in the Appendix, also replace the image string
`gcr.io/google-samples/redis-bq-pipe:v5` with the name of the container image that you have built and pushed.)

### Deploy your app

After starting up your GKE cluster, and configuring your `.yaml` files, run the following from the `redis` directory.
First create the Redis service and Redis master deployment:

```sh
kubectl create -f redis-master-service.yaml
kubectl create -f redis-master.yaml
```

Ensure the pod and service are running:

```sh
kubectl get pods
kubectl get services
```

Next, create the other deployments:

```sh
kubectl.sh create -f bigquery-controller.yaml
kubectl.sh create -f twitter-stream.yaml
```

To see your running pods, run:

```sh
kubectl get pods -o wide
```

You'll see a list of the pods that are running, the containers they're using, and the node they're running on in the cluster.
Because the `bigquery-controller` Deployment has specified two replicas, you will see two pods running with names like `bigquery-controller-xxxx`.

You can see whether each pod is `Running` or `Pending`.  If a pod isn't moving into
the `Running` state after about a minute, that is an indication that it isn't starting up properly.
See the ["Troubleshooting"](#troubleshooting) section below.

You can run:

```sh
kubectl get deployments
```

to see the system's defined deployments, and how many replicas each is specified to have.

You can also use the [Kubernetes Dashboard](https://github.com/kubernetes/dashboard) interface to inspect your cluster and its components.  Do this by running:

```sh
kubectl proxy
```

then navigating to the following location in your browser: [http://localhost:8001/ui](http://localhost:8001/ui).

#### Optional: resize the `bigquery-controller`

For fun, try resizing `bigquery-controller` once its pods are running:

```sh
kubectl scale --replicas=3 deployment bigquery-controller
```

You should see an additional third pod running shortly.

Note: don't resize the `twitter-stream-controller`.  You should only open up one Twitter streaming connection for an app at a time.

## Query your BigQuery table

After setting up your pipeline, let it collect tweets for a while – a few hours
should do, but the longer you let it run, the richer your data set will be. After
you have some data in your BigQuery table, you can try running some
sample queries.  

[Visit the BigQuery console](https://bigquery.cloud.google.com/)
and click **Compose Query** to begin writing a new query. In the following, replace `your-dataset-name` with the actual name of your dataset, and `tweets` with your table if you named it differently.

This example query
demonstrates how to find the most retweeted tweets in your table, filtering on a
specific term (in this case, "android"):


```sql
SELECT
  text,
  MAX(retweeted_status.retweet_count) AS max_retweets,
  retweeted_status.user.screen_name
FROM
  `your-dataset-name.tweets` 
WHERE
  LOWER(text) LIKE '%android%'
GROUP BY
  text,
  retweeted_status.user.screen_name
ORDER BY
  max_retweets DESC
LIMIT
  1000
```

You might also find it interesting to filter your collected tweets by a set of
terms. The following query filters by the words "Kubernetes," "BigQuery,"
or "Redis" (case-insensitive):

```sql
SELECT
  created_at,
  text,
  id,
  retweeted_status.retweet_count,
  user.screen_name
FROM
  `your-dataset-name.tweets` 
WHERE
  LOWER(text) LIKE '%kubernetes%'
  OR LOWER(text) LIKE '%bigquery%'
  OR LOWER(text) LIKE '%redis%'
ORDER BY
  created_at DESC
LIMIT
  1000
```  

The following query looks for a correlation between the number of favorites and
the number of retweets in your set of tweets, grouped by language:

```sql
SELECT
  CORR(retweeted_status.retweet_count, retweeted_status.favorite_count),
  lang,
COUNT(*) c
FROM `your-dataset-name.tweets` 
GROUP BY lang
HAVING c > 2000000
ORDER BY 1
```

You could also investigate whether the speakers of a specific
language prefer favoriting to retweeting, or vice versa:

```sql
SELECT
  CORR(retweeted_status.retweet_count, retweeted_status.favorite_count),
  lang,
COUNT(*) c,
AVG(retweeted_status.retweet_count) avg_rt,
AVG(retweeted_status.favorite_count) avg_fv,
AVG(retweeted_status.retweet_count)/AVG(retweeted_status.favorite_count) ratio_rt_fv
FROM `your-dataset-name.tweets` 
WHERE retweeted_status.retweet_count > 1 AND retweeted_status.favorite_count > 1
GROUP BY lang
HAVING c > 1000000
ORDER BY 1;
```


## Shut down your replicated pods and cluster

Labels make it easy to select the resources you want to stop or delete, e.g.:

```shell
kubectl delete deployment -l "name in (twitter-stream, bigquery-controller, redis-master)"
```


If you'd like to shut down your cluster altogether, you can delete it in the [Cloud Console](https://console.cloud.google.com) (or [from the command line](https://cloud.google.com/sdk/gcloud/reference/container/clusters/delete)).
Be sure to do this when you're done with it, so that you don't get charged.


## Troubleshooting

You can inspect the components of your cluster in the Kubernetes dashboard by running:

```sh
kubectl proxy
```


To confirm that all your nodes, services, pods, and deployments are up and
running properly, you can run the following commands from the command line:

```sh
kubectl get nodes
kubectl get svc
kubectl get pods
kubectl get deployments
```

For the pods, you can see whether each pod is `Running` or `Pending`.  If a pod isn't moving into
the `Running` state after about a minute, that is an indication that it isn't starting up properly.

Double check that the pods show that they are using the correct container image name.
You may also want to double check your .yaml file edits.

If nothing is obvious, a good next step is to look at the pod logs. You can do this from your local machine via:

```shell
kubectl logs <pod-name>
```

You can also [get a shell to a running container](https://kubernetes.io/docs/tasks/debug-application-cluster/get-shell-running-container/). 

If you don't see evidence that your container has ever started sucessfully, double check the name of the container image that the pod is using, and make sure that you have pushed a container with that tag to the container registry.


## Appendix: Optional: Use a customized Docker image for your app

This step is optional.

The example app uses a [Docker](https://www.docker.com/) image that runs the app's python scripts. 
If you like, you can just use the prebuilt docker image, `gcr.io/google-samples/redis-bq-pipe:v5`, for your app. This is the image used by default in the `bigquery-controller.yaml` and `twitter-stream.yaml` files.

Follow the instructions below if you'd like to add customization and use your own image instead.
For this, you'll either need [Docker](https://docs.docker.com/installation/#installation) installed locally, or you can run Docker in the Cloud Shell. (You could also alternately use [Google Cloud Container Builder](https://cloud.google.com/container-builder/docs/).)

Once the image is built, it needs to be pushed somewhere that Kubernetes can access it. We'll use the [Google Container
Registry](https://cloud.google.com/tools/container-registry/) (GCR). It uses a Google Cloud Storage bucket in your own project to store the images, for privacy and low latency.  The GCR [docs](https://cloud.google.com/tools/container-registry/) provide more information on GCR and how to push images to it.

To build and push your Docker image to GCR, cd to the `redis-pipe-image` subdirectory, and run the following series of commands.

First, build your image, replacing `<your-project-name>` with your project name:

```sh
gcr.io/<your-project-name>/redis-bq-pipe:v1
```

This builds your image according to the specifications of the `Dockerfile` in that directory. (You can name your image something other than 'redis-bq-pipe' if you want).

Then, push your image to the
[Google Container Registry](https://cloud.google.com/tools/container-registry/) (GCR), again
replacing `<your-project-name>` with your project:

```sh
gcloud docker -- push gcr.io/<your-project-name>/redis-bq-pipe:v1
```

Finally, edit `twitter-stream.yaml` and `bigquery-controller.yaml`, and
replace `gcr.io/google-samples/redis-bq-pipe:v5` with the name of your image.












