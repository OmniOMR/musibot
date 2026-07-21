# Who are the users

There are three kinds of users, ordered by their priority:


## 1. Libraries and memory institutions

Libraries hold millions of pages of old handwritten or printed music documents. These have already been scanned at 300 DPI and above as JPEG files. In order to understand what music is in those documents, libraries may connect to a running instance of Musibot (e.g. via the python client) and batch-process all of their collections. They may use the resulting MusicXML to extract lead melodies that can be used for search, and duplicate identification.

Libraries will create occasional bursts of requests (say, a week-long streak to process all of their collections with a newer pipeline) which creates the requirement for horizontal scalability of Musibot workers. However, these bursts will be coordinated with the maintainer of a running Musibot instance, so this scaling does not need to be automatic.

Libraries may also create a steady weak load from recognition of documents that are newly added to the library.


## 2. OMR Model developers

When OMR researchers train new recognition models, Musibot serves as a place where to deploy these models (either publicly or internally). Deploying models to the service provides number of benefits:

- The model developer must set up only one runtime environment - the Musibot worker and everyone on the team may then use the model remotely from any machine via the Musibot python client.
- The team may set up a centralized benchmarking rig that can thoroughly evaluate each model variant through a unified Musibot API, decoupling model development from its final evaluation.
- Deploying the model to production then becomes a simple switch of a boolean flag.

Of course, not all models have to be deployed to Musibot. When a developer trains a model and tunes hyperparameters, he/she compares these models based on some good-enough metric (say edit distance on output tokens), however, when the best model is picked, it may be deployed and a separate testing rig may compute the MusicXML-level metrics, document retrieval metrics, or judge the model's performance in the context of a complete recognition pipeline.


## 3. General public

The developer team that trains OMR models searches for funding, customers, and/or grant application partners. They want to present their models (and the whole pipeline) at conferences, as well as being able to email a URL link to the deployed service for outsiders to try out. For this reason Musibot also provides a web UI and a small usage allowance for general public. This exposure may also spill over and benefit unforseen third-parties, such as music teachers and hobby musicians, who may use Musibot to recognize their own music materials so that they may edit it, or just re-print it.
