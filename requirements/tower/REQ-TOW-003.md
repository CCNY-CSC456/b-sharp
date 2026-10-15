# REQ-TOW-003: Message Cycle

The message system shall use a connection pool architecture managed by the tower.
- the pool owner shall maintain a persistent database connection.
- the system shall have a well-defined message cycle to maintain service guarentees.
- the message cycle shall consist of the following stages: RECEIPT, FLUSH, DISPATCH, REARM. 
- the pool owner will flush (persist) messages to disk in bulk based on real-time requirements during FLUSH.
- the pool owner will send ACK ("acknowledgements") for flushed messages in DISPATCH.
- RECEIPT and REARM remain unspecified at this time.