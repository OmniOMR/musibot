# Domain model

The domain model of Musibot is the following:

```mermaid
---
config:
    class:
        hideEmptyMembersBox: true
---
classDiagram
    class User
    class MusicorpusPage
    class PipelineExecution
    class Pipeline
    class Orchestrator
    class Model
    class Worker

    User "1" --> "*" MusicorpusPage
    MusicorpusPage "1" --> "*" PipelineExecution
    PipelineExecution "*" --> "1" Pipeline
    Orchestrator "1" --> "*" PipelineExecution
    Pipeline "*" --> "*" Model
    Worker "1" --> "1" Model
```

**User** is the person/entity who is accessing Musibot via its API.

**MusicorpusPage** is all the data associated with a single scanned page (or a part of it), following the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md). It starts out containing only the scan of the page as a JPEG file and then a recognition *Pipeline* is executed to provide additional data. Finally, the *User* downloads this additional data after the *PipelineExecution* finishes.

**PipelineExecution** is one execution of some *Pipeline* against some data in the form of a *MusicorpusPage*. The execution generates new data that is added to the *MusicorpusPage*.

**Pipeline** is a specific sequence of operations and *Model* invocations that produces some new data (e.g. MusicXML or COCO page layout boxes) from some existing input data (page JPEG scan). A *Pipeline* is represented in code by an `async` python function and is held only in memory when executing (*PipelineExecution*) for up to a few minutes.

**Orchestrator** is the part of the python codebase (which may or may not be a separate service/services) responsible for executing *Pipelines*. By executing a *Pipeline* it orchestrates the runtime of individual *Models*.

**Model** is a specific OMR model (in a specific version) used by pipelines to perform recognition work (i.e. transcribing a single staff of music to MusicXML).

**Worker** is a separate operating system process (on the same or other machine) responsible for executing one specific *Model*. It provides the specific runtime environment needed for that specific *Model*.
