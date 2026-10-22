
# Why is the messaging system in Tower?
- ostentiably, ensuring Tower has the control it needs to safely schedule.
- in practice, there wasn't a better place to put it.


# What does "Persistent Polling Process Event Loop" even mean?
- here's a rough LLM generated ASCII state chart:
```txt
                  +-------------------+
                  |       IDLE        |
                  +---------+---------+
                            |
                            | Request Lock
                            v
                  +-------------------+
            +---->|   POLLING / WAIT  |<----+
            |     +---------+---------+     |
            |               |               |
            | Expired       | Acquired      | Jittered Backoff
            |               v               |
   +--------+--------+  +---+---------------+----+
   |  ACQUIRE_FAILED |  |      HELD / BUSY       |
   +-----------------+  +-----------+------------+
                                    |
                                    | Release / TTL
                                    v
                        +-------------------+
                        |     RELEASED      |
                        +-------------------+
                        
```

- happy path gist is **IDLE**, **POLL**, **HOLD**, **FREE** 
- note that the actual "polling" (retreiveal) of the shared resource (database) 
happens in the **HOLD** state because the process *holds* the resource lock