# REQ-TOWER-014

The tower subsystem shall have a persistent event-loop polling process.
- The process will poll the tower message queue at a regular interval.
- The exact time interval is left unspecified to accommodate changing requirements.
- The polling process must not starve other polling process of resource access.
- The polling process must have some communication channel with other polling
processes outside the contended resource.
- The process may fail gracefully on some given number of polling loops for
some specified interval.
- The process may not exceed some given number of poll failures per polling loop
for some specified interval.
- The liveness interval during which all polling processes must have at least
one success is left unspecified at this time.


