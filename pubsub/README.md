
Copyright (C) 2014 Google Inc.

# Example app: Real-time data analysis using Kubernetes, PubSub, and BigQuery

This directory contains an example [Kubernetes](https://github.com/GoogleCloudPlatform/kubernetes) app that shows how to build a 'pipeline' to stream data into BigQuery.
The pipeline uses uses [Google Cloud PubSub](https://cloud.google.com/pubsub/docs).

See also a related app, in the `redis` directory, which uses [Redis](http://redis.io/) instead of PubSub.

**More detailed documentation for this PubSub example is coming soon**.
However, the general structure of the example is similar to that of the Redis example, described [here](https://cloud.google.com/solutions/real-time-analysis/kubernetes-redis-bigquery), except that you will be configuring the app to use PubSub instead of Redis.

The primary setup differences are listed below.

## Configuring the example

### Start up your Kubernetes cluster with the 'Cloud Platform' scope.

As described in the Redis-based [tutorial](https://cloud.google.com/solutions
/real-time-analysis/kubernetes-redis-bigquery), edit the MINION_SCOPES in
`cluster/gce/config-default.sh` before starting up your cluster.  For the
PubSub example, you will need to **add the `cloud-platform` scope as well as
`bigquery`**.

```
MINION_SCOPES=("storage-ro" "compute-rw" "bigquery" "https://www.googleapis.com/auth/cloud-platform")
```

(You don't need to make the startup script changes to `cluster/gce/util.sh` as
described in the tutorial if you do not plan to run the Redis variant of this
example).


### Set up a PubSub topic in your project

Before running the example, in addition to the Twitter and BigQuery
configuration described in the tutorial, you will need to **create a PubSub
topic** in your Cloud project. An easy way to do this is via the *API explorer*, in the "Try It!" section on [this page](https://cloud.google.com/pubsub/reference/rest/v1beta2/projects/topics/create).  With the `v1beta2` API, specify your topic name like this: `projects/your-project/topics/your-topic`.

### Configure the Kubernetes .yaml files

Configure the `bigquery-controller.yaml` and `twitter-stream.yaml` files in the `pubsub` directory with
your config information.  You will need to specify the name of your PubSub topic as
well as adding other config info as described in the [Redis-based tutorial](https://cloud.google.com/solutions/real-time-analysis/kubernetes-redis-bigquery).
However, for this example, you won't be using Redis itself, and don't need the
Redis `pod` and `service` config files mentioned in the tutorial.

## Building your Docker images, and using the Google Container Registry

As part of the installation process, you will build a [Docker](https://www.docker.com/) image, containing the
Python scripts, to be used by your Kubernetes app. You will then specify that image in the app's .yaml config files.

The basic Docker image build process is described in the [tutorial](https://cloud.google.com/solutions/real-time-analysis/kubernetes-redis-bigquery); for this PubSub
example, use the `Dockerfile` and assets in the `pubsub/pubsub-pipe-image` directory for your image.

You can now use the new [Google Container
Registry](https://cloud.google.com/tools/container-registry/) (GCR), which is in Beta, for
your Docker images if you like.  With GCR, your images are stored in your
own project, using GCS.
See the GCR [docs](https://cloud.google.com/tools/container-registry/) for
details.

## Starting up and turning down your app's pods

After starting up your Kubernetes cluster, and configuring your `pubsub/*.yaml` files, you can run the pipeline by starting the replicated pods like this from the `pubsub` directory (the following assumes you've put
`<path-to-kubernetes>/cluster` in your path):


    kubectl.sh create -f bigquery-controller_filter.yaml
    kubectl.sh create -f twitter-streamf.yaml

Again, see the [tutorial](https://cloud.google.com/solutions/real-time-analysis/kubernetes-redis-bigquery) for more information on replicated pods.
You can shut down the replicated pods like this.

    kubectl.sh resize --replicas=0 replicationControllers bigquery-controller
    kubectl.sh resize --replicas=0 replicationControllers twitter-stream-controller
    kubectl.sh delete replicationControllers bigquery-controller
    kubectl.sh delete replicationControllers twitter-stream-controller
