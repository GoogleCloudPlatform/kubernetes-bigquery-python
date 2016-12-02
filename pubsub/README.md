
Copyright (C) 2014 Google Inc.

# Example app: Real-time data analysis using Kubernetes, PubSub, and BigQuery

- [Introduction](#introduction)
- [Prerequisites and initial setup](#prerequisites-and-initial-setup)
  - [Install Docker](#install-docker)
  - [Create and configure a new Google Cloud Platform project](#create-and-configure-a-new-google-cloud-platform-project)
  - [Set up the Google Cloud SDK](#set-up-the-google-cloud-sdk)
  - [Create a BigQuery table](#create-a-bigquery-table)
  - [Create a Twitter application and access token](#create-a-twitter-application-and-access-token)
  - [Set up a PubSub topic in your project](#set-up-a-pubsub-topic-in-your-project)
  - [Install Kubernetes, and configure and start a Kubernetes cluster](#install-kubernetes-and-configure-and-start-a-kubernetes-cluster)
- [Configure your app](#configure-your-app)
  - [Optional: Build and push a Docker image for your app](#optional-build-and-push-a-docker-image-for-your-app)
  - [Kubernetes pod, Replica Set, and Deployment configuration](#kubernetes-pod-replica-set-and-deployment-configuration)
    - [Deployment configuration](#deployment-configuration)
- [Starting up your app](#starting-up-your-app)
  - [Listing your running pods and Deployments](#listing-your-running-pods-and-deployments)
  - [Resizing the `bigquery-controller`](#resizing-the-bigquery-controller)
- [Query your BigQuery table](#query-your-bigquery-table)
- [Shut down your replicated pods and cluster](#shut-down-your-replicated-pods-and-cluster)
- [Troubleshooting](#troubleshooting)

## Introduction

This directory contains an example [Kubernetes](https://github.com/GoogleCloudPlatform/kubernetes) app that shows how to build a 'pipeline' to stream Twitter data into [BigQuery](https://cloud.google.com/bigquery/what-is-bigquery), via [Google Cloud PubSub](https://cloud.google.com/pubsub/docs).

[Kubernetes](http://github.com/GoogleCloudPlatform/kubernetes)
is an open source orchestration system for Docker containers.
We won't go into much detail about Kubernetes' features in this tutorial, but please see its [docs](https://github.com/GoogleCloudPlatform/kubernetes/tree/master/docs) for much more information.


[Bigquery](https://cloud.google.com/bigquery/what-is-bigquery)  lets you run fast, SQL-like queries against multi-terabyte datasets in seconds, using the processing power of Google's infrastructure.

[PubSub](https://cloud.google.com/pubsub/overview) provides many-to-many, asynchronous messaging that decouples senders and receivers. It allows for secure and highly available communication between independently written applications and delivers low-latency, durable messaging.

The app uses uses PubSub to buffer the data coming in from Twitter and to decouple ingestion from processing.
One of the Kubernetes app ***pods*** reads the data from Twitter and publishes it to a PubSub topic.  Other pods subscribe to the PubSub topic, grab data in small batches, and stream it into BigQuery.  The figure below suggests this flow.

<img src="http://amy-jo.storage.googleapis.com/images/k8s_pubsub_tw_bq.png" width="680">

This app can be thought of as a 'workflow' type of app-- it doesn't have a web
front end (though Kubernetes is great for those types of apps as well).
Instead, it is designed to continously run a scalable data ingestion pipeline.
Note that PubSub provides [guaranteed at-least-once message
delivery](https://cloud.google.com/pubsub/overview#benefits).  This means that
we might sometimes see a duplicated item, but as each tweet has a UID, that's
not an issue for this example.

See also a related app, in the `redis` directory of this repo, which uses
[Redis](http://redis.io/) instead of PubSub. The general structure of this
example is similar in many respects to that of the Redis example, which is
described [here](https://cloud.google.com/solutions/real-time-analysis
/kubernetes-redis-bigquery), except that you will be configuring the app to
use PubSub instead of Redis.  Much of the setup is the same between the two
examples.

Note: This tutorial uses several **billable components** of Google Cloud
Platform. The cost of running this tutorial will vary depending on run time.
New Cloud Platform users may be eligible for a [free trial](/free-trial).

## Prerequisites and initial setup

First, [download and unzip the code for this example](https://github.com/GoogleCloudPlatform/kubernetes-bigquery-python/archive/master.zip), if you haven't already.
If you prefer, you can clone the Github repository instead:

    $ git clone https://github.com/GoogleCloudPlatform/kubernetes-bigquery-python.git

This example is in the `pubsub` subdirectory of that repository.
For convenience, you may want to point an environment variable to that directory:

    $ export EXAMPLE_DIR=local/path/to/kubernetes-bigquery-python-directory/pubsub

The rest of the prerequisites for this example, described below, are:

 - install Docker
 - create and configure a Google Cloud Platform project
 - set up the Google Cloud SDK
 - create a BigQuery table to hold the results
 - create a Twitter 'application' so that you can access the Twitter streaming API to pull in tweets
 - set up a PubSub topic in your Cloud project
 - install Kubernetes

Note: This tutorial assumes that you're running Linux or MacOS, but hasn't yet been tested on Windows.

### Install Docker

This app requires that you have
[Docker](https://docs.docker.com/installation/#installation) installed locally.  This is because you will build a custom Docker image for your Kubernetes app.  Follow the installation instructions on the docker site.

### Create and configure a new Google Cloud Platform project

To work through this example, you must have a Google Cloud Platform project with
the required APIs enabled. In the [Cloud Developers Console](https://console.developers.google.com),
create a new project or choose an existing project, then in the `APIs & auth > APIs` panel,
enable the BigQuery, Google Compute Engine, PubSub, Google Cloud Storage, and Google Cloud Storage JSON APIs.
You will be prompted to enable billing if you have not previously done so.

### Set up the Google Cloud SDK

This tutorial uses the [Google Cloud SDK](https://cloud.google.com/sdk/) to interact with the Cloud Platform from
your local terminal. Follow the instructions on that page to install the Cloud SDK.

**Enable preview features** in the gcloud tool, as follows:

    $ gcloud components update preview

and **authenticate** using your Google Account:

    $ gcloud auth login

After authorizing, **set the default project** for the Cloud SDK to the
project you selected in the previous section of this tutorial:

    $ gcloud config set project <project_id>


### Create a BigQuery table

Next, create a BigQuery table to store your tweets. BigQuery groups
tables into abstraction layers called datasets, so first create a dataset as necessary.  You can do this from the web UI, or from the command line like this:

    $ bq mk <your-dataset-name>

The `bq` command line tool is included in the Cloud SDK.

If you prefer, you can use an existing project dataset instead.

Then, create a new table (e.g., `tweets`) in that
dataset, to contain your incoming tweets. Each BigQuery table must be defined by
a schema. This example includes a predefined schema in the `<example_root>/bigquery-setup` subdirectory,
`schema.json`, that you can use to define your table:

    $ bq mk -t <your-dataset-name>.tweets <example_root>/bigquery-setup/schema.json

(If you prefer, you can also create your table via the web UI, pasting in the schema from `schema.json`).

### Create a Twitter application and access token

To use the Twitter API, you need to create a Twitter application.

[Create a Twitter account](https://twitter.com/signup) as necessary, then
[create a Twitter application.](https://apps.twitter.com/).

In the Twitter Application Management page, navigate to the **Keys and
Access Tokens** tab.  Note your `Consumer Key` and `Consumer Secret`.

Then, click the **Create my access token** button to create a new access token, and note your
`Access Token` and `Access Token Secret`.

### Set up a PubSub topic in your project

Before running the example, in addition to the Twitter and BigQuery
configuration described in the tutorial, you will need to **create a PubSub
topic** in your Cloud project. An easy way to do this is via the *API explorer*, in the "Try It!" section on [this page](https://cloud.google.com/pubsub/reference/rest/v1beta2/projects/topics/create).  With the `v1beta2` API, specify your topic name like this: `projects/your-project/topics/your-topic`.

Note down the name of the topic you made.

### Install Kubernetes, and configure and start a Kubernetes cluster

[Download the latest Kubernetes binary release](https://github.com/GoogleCloudPlatform/kubernetes/releases/latest)
and unpack it into the directory of your choice.

Make one change before you start up the Kubernetes cluster: **edit the `NODE_SCOPES`** in
`<kubernetes>/cluster/gce/config-common.sh` before starting up the cluster, to let your instances auth with BigQuery and PubSub:

```
NODE_SCOPES="${NODE_SCOPES:-compute-rw,monitoring,logging-write,storage-ro,bigquery,https://www.googleapis.com/auth/pubsub}"

```

Then, see [this section](https://github.com/GoogleCloudPlatform/kubernetes/blob/master/docs/getting-started-guides/gce.md#installing-the-kubernetes-command-line-tools-on-your-workstation) of the GCE "getting started" guide to set up access to the `kubectl` command-line tool in your path. As noted in that guide, `gcloud` also ships with kubectl, which by default is added to your path. However the `gcloud` bundled kubectl version may be older, and we recommend that you use the downloaded binary to avoid potential issues with client/server version skew.

Then, start your cluster as described in the [Kubernetes documentation](https://github.com/GoogleCloudPlatform/kubernetes/tree/master/docs), e.g.:

    $ <kubernetes>/cluster/kube-up.sh

This starts up a set of Kubernetes *nodes*, using Compute Engine VMs.  Then, a bit later in this tutorial, we'll start up some Kubernetes *pods* on the nodes.

If you have cluster startup issues, double check that you have set your default cloud project via `gcloud` as described above:
`gcloud config set project <project_id>`.

## Configure your app

Now you're ready to configure your app.  This involves two things: optionally building a Docker image to be used by the app, and editing two Kubernetes *replication controller* config files with your configuration information.

### Optional: Build and push a Docker image for your app

If you like, you can use the prebuilt docker image, `gcr.io/google-samples/pubsub-bq-pipe:v3`, for your app. This is the image used by default in the `bigquery-controller.yaml` and `twitter-stream.yaml` files.

Follow the instructions below if you'd like to build and use your own image instead.

This Kubernetes app uses a [Docker](https://www.docker.com/) image that runs the app's python scripts.  (An environment variable set in the Deployment specification files, `PROCESSINGSCRIPT`, indicates which script to run).  Once the image is built, it needs to be pushed somewhere that Kubernetes can access it.  For this example, we'll use the new [Google Container
Registry](https://cloud.google.com/tools/container-registry/) (GCR), in Beta. It uses a Google Cloud Storage bucket in your own project to store the images, for privacy and low latency.  The GCR [docs](https://cloud.google.com/tools/container-registry/) provide more information on GCR and how to push images to it.  You can also push your
images to, e.g., the Docker Hub.

To build and push your Docker image to GCR, cd to the `pubsub-pipe-image` subdirectory, and run the following series of commands.  (As noted above, a prerequisite is that you have Docker running locally).

First, build your image:

    $ docker build -t user/pubsubpipe .

This builds your image according to the specifications of the `Dockerfile` in that directory. (You can name your image something other than 'pubsubpipe').
If you take a look at the `Dockerfile`, you can see that it installs some Python libraries as well as adding app scripts to the image.

Then, tag your image for GCR, using your project name. You can combine these two steps if you want.

    $ docker tag -f user/pubsubpipe gcr.io/your_project_name/pubsubpipe

`gcr.io/your_project_name` is your registry location. If your project name has hyphens, replace them with dashes in your tag, as described in the [docs](https://cloud.google.com/tools/container-registry/#preparing_your_docker_image).
Finally, use `gcloud` to push your image to GCR, using the tag name you created:

    $ gcloud docker push gcr.io/your_project_name/pubsubpipe


### Kubernetes pod, Replica Set, and Deployment configuration

In Kubernetes, [**pods**](https://github.com/GoogleCloudPlatform/kubernetes/blob/master/docs/pods.md)-- rather than individual application containers-- are the smallest deployable units that can be created, scheduled, and managed.

A [**replica set**](http://kubernetes.io/docs/user-guide/replicasets/) ensures that a specified number of pod "replicas" are running at any one time. If there are too many, it will kill some. If there are too few, it will start more. As opposed to just creating singleton pods or even creating pods in bulk, a replica set replaces pods that are deleted or terminated for any reason, such as in the case of node failure.

A [Deployment](http://kubernetes.io/docs/user-guide/deployments/) provides declarative updates for Pods and Replica Sets. You only need to describe the desired state in a Deployment object, and the Deployment controller will change the actual state to the desired state at a controlled rate for you.
We will use Deployments for both parts of our Kubernetes app.  The first, specified by `twitter-stream.yaml`, defines one replica of a container that will read in tweets via the Twitter streaming API and dump them to a PubSub topic. We're only using one replica here so that we don't open up multiple Twitter API connections on the same app.  However, we're still using a replicated pod for the robustness that gives us-- if the pod crashes for some reason, it will be restarted, since will specify that there should always be one running.

The second part of the app, specified by `bigquery-controller.yaml`, defines two replicas of a container that will subscribe to the same PubSub topic, pull off tweets in small batches, and insert them into a BigQuery table via the BigQuery Streaming API.  Here, we can use multiple pods-- they will use the same subscription to read from the PubSub topic, thus distributing the load. If source throughput were to increase, we could increase the number of these  `bigquery-controller` pods.

#### Deployment configuration

Edit `$EXAMPLE_DIR/twitter-stream.yaml`.  Set your `PUBSUB_TOPIC` to the name of the topic you created.
Then, set the Twitter authentication information to the values you noted when setting up your Twitter application (`CONSUMERKEY`,`CONSUMERSECRET`, `ACCESSTOKEN`, `ACCESSTOKENSEC`).  Then, if you built your own docker image, replace the image string `gcr.io/google-samples/pubsub-bq-pipe:v3` with the name of the image that you have created and pushed.

Edit `$EXAMPLE_DIR/bigquery-controller.yaml`.  Set your `PUBSUB_TOPIC`, and set your `PROJECT_ID`, `BQ_DATASET`, and `BQ_TABLE` information.  Then, if you built your own docker image, replace the image string `gcr.io/google-samples/pubsub-bq-pipe:v3` with the name of the image that you have created and pushed.

## Starting up your app

After starting up your Kubernetes cluster, and configuring your `pubsub/*.yaml` files, you can run the pipeline by starting the replicated pods like this from the `pubsub` directory (the following assumes you've put
`<path-to-kubernetes>/cluster` in your path; if not, use the full path):


    $ kubectl.sh create -f bigquery-controller.yaml
    $ kubectl.sh create -f twitter-stream.yaml

### Listing your running pods and Deployments

To see your running pods, run:

    $ kubectl get pods

(Again, this assumes you've put `<path-to-kubernetes>/cluster` in your path)

You'll see a list of the pods that are running, the containers they're using, and the node they're running on in the cluster. You'll see some pods started by the system, as well as your own pods. Because the `bigquery-controller` Deployment has specified two replicas, you will see two pods running with names like `bigquery-controller-xxxx`.

You can see whether each pod is `Running` or `Pending`.  If a pod isn't moving into
the `Running` state after about a minute, that is an indication that it isn't starting up properly.  See the "Troubleshooting" section below.

You can run:

    $ kubectl get deployments

to see the system's defined deployments, and how many replicas each is specified to have.

### Resizing the `bigquery-controller`

For fun, try resizing `bigquery-controller` once its pods are running:

    $ kubectl scale --replicas=3 deployment bigquery-controller

You should see an additional third pod running shortly.

Note: don't resize the `twitter-stream-controller`.  You should only open up one Twitter streaming connection for an app at a time.

## Query your BigQuery table

After setting up your pipeline, let it collect tweets for a while – a few hours
should do, but the longer you let it run, the richer your data set will be. After
you have some data in your BigQuery table, you can try running some
sample queries.  In the following, replace `your-dataset-name` with the actual name of your dataset.

[Visit the BigQuery console](https://bigquery.cloud.google.com/)
and click **Compose Query** to begin writing a new query. This example query
demonstrates how to find the most retweeted tweets in your table, filtering on a
specific term (in this case, "android"):

    SELECT
      text,
      MAX(retweeted_status.retweet_count) AS max_retweets,
      retweeted_status.user.screen_name
    FROM
      [your-dataset-name.tweets]
    WHERE
      text CONTAINS 'android'
    GROUP BY
      text,
      retweeted_status.user.screen_name
    ORDER BY
      max_retweets DESC
    LIMIT
      1000 IGNORE CASE;

You might also find it interesting to filter your collected tweets by a set of
terms. The following query filters by the words "Kubernetes," "BigQuery,"
"Redis," or "Twitter:"

    SELECT
      created_at,
      text,
      id,
      retweeted_status.retweet_count,
      user.screen_name
    FROM
      [your-dataset-name.tweets]
    WHERE
      text CONTAINS 'kubernetes'
      OR text CONTAINS 'BigQuery'
      OR text CONTAINS 'redis'
      OR text CONTAINS 'twitter'
    ORDER BY
      created_at DESC
    LIMIT
      1000 IGNORE CASE;

The following query looks for a correlation between the number of favorites and
the number of retweets in your set of tweets:

    SELECT
      CORR(retweeted_status.retweet_count, retweeted_status.favorite_count),
      lang,
    COUNT(*) c
    FROM [your-dataset-name.tweets]
    GROUP BY lang
    HAVING c > 2000000
    ORDER BY 1

You could also investigate whether the speakers of a specific
language prefer favoriting to retweeting, or vice versa:

    SELECT
      CORR(retweeted_status.retweet_count, retweeted_status.favorite_count),
      lang,
    COUNT(*) c,
    AVG(retweeted_status.retweet_count) avg_rt,
    AVG(retweeted_status.favorite_count) avg_fv,
    AVG(retweeted_status.retweet_count)/AVG(retweeted_status.favorite_count) ratio_rt_fv
    FROM [your-dataset-name.tweets]
    WHERE retweeted_status.retweet_count > 1 AND retweeted_status.favorite_count > 1
    GROUP BY lang
    HAVING c > 1000000
    ORDER BY 1;


## Shut down your replicated pods and cluster

Labels make it easy to select the resources you want to stop or delete, e.g.:

```shell
kubectl delete deployment -l "name in (twitter-stream, bigquery-controller)"
```


If you'd like to shut down your cluster instances altogether, run the following
command:

    <kubernetes>/cluster/kube-down.sh

This takes down all of the instances in your cluster.

## Troubleshooting

In addition to the info here, also see the [Troubleshooting](https://github.com/GoogleCloudPlatform/kubernetes/blob/master/docs/troubleshooting.md) page in the Kubernetes docs.

To confirm that all your nodes, pods, and deployments are up and
running properly, you can run the following commands:

    $ kubectl get nodes
    $ kubectl get pods
    $ kubectl get deployments

For the pods, you can see whether each pod is `Running` or `Pending`.  If a pod isn't moving into
the `Running` state after about a minute, that is an indication that it isn't starting up properly.

Double check that the pods show that they are using the correct container image name.
You may also want to double check your .yaml file edits.

If nothing is obvious, a good next step is to look at the pod logs.

You can do this most easily from your local machine via:

```shell
$ kubectl logs <pod-name>
```

You can also ssh into a node and look directly at the docker logs there.
To do this, first find the node a pod is running on:

```shell
$ kubectl describe pods/<pod-name>
```

In the output, look for the `HOST` information for the pod of interest.  It should look something like
(`kubernetes-minion-<xxxx>`). SSH into the instance:

    $ gcloud compute --project "<your-project-name>" ssh --zone "<your-project-zone>" "kubernetes-minion-<xxxx>"

Note: If you don't remember the zone your instances are running in, run
`gcloud compute instances list` from the command line or visit the
VM instances page in the [Developers Console](https://console.developers.google.com).

After logging into a node, become the root user:

    $ sudo -s

Run the following command to see all currently-running containers and how long
they've been running:

    $ docker ps

Look for the running containers associated with your pods, and note their container IDs.
To look at their logs or inspect their settings, run the following commands
respectively:

    $ docker logs <container_id>
    $ docker inspect <container_id>

Because of the way the output for the containers is buffered, you may not see log content right away.  However, if there was a startup error, that should be evident.

If you don't see a running container for a given pod, that may mean that it is not starting up properly. In that case, the replication controller will keep trying to restart it.

Run the following to list all containers:

    $ docker ps -a

Look at the container names and see if any of your app containers are exiting rather than starting up properly.  If they are, running

    $ docker logs <container_id>

should show what's wrong.

If you don't see evidence that your container has ever started sucessfully, double check the name of the container image that the pod is using, and make sure that you have pushed a container with that tag to the container registry.















