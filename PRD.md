Goal: Audit Silent Payments Indexer Tweak Services to determine which services are producing the most accurate tweak data. 

Requirements:
- The auditor should be written in python
- Stop working and ask me for confirmation before making large decisions - you can handle the easy straight forward logic
- Each index service requires a different connection method. some will be http others rpc. the request parameters and response data have different formats.
	- provide a template or interface for each index service to make the request and process a response
	- I have prototype template scripts that make the request for to each index service.
		- Each index service response will need to be normalized to a format for storage of results and comparison
- the service auditor will accept a block or range of blocks to audit given a height
- Handling results
	- For each block I want to know the total number of tweaks returns for each index service
		- Additionally I want to know how many of the tweaks match
			- providing a set of matching, non matching by indexing service would be great

## Session Input Prompts Log

### BlindBit gRPC Service Implementation Session

**Initial Request:**
```
I want to add a new service implementation for testing blindbits new gRPC service endpoints.

the protobuf definitions can be found here: github.com/setavenger/blindbit-lib/proto/pb

for each step in the plan provid me with a list of actions and wait for confirmation or edits before continuing

let me know if you have any questions or need clarification along the way

speed is not important, precision is valued
```

**User Responses to Implementation Questions:**
```
responses to questions:
1. implement both - endpoint config will select the correct 1
2. gRPC server on host 127.0.0.1:50051 and http://127.0.0.1:8000
3. https://github.com/setavenger/blindbit-lib/tree/master/proto/pb
4. no auth
5. lets handle streaming later - but yes it will be important

If my answers don't change the plan above you can perform steps 1-5
```

**Additional Context Provided:**
```
[Request interrupted by user for tool use]I have downloaded blindbit-oracle at /Users/ron/src/blindbit-oracle/
```

**Permission to Continue:**
```
[Request interrupted by user for tool use]proceed with the suggested change above to service_implementations.py
```





review the #codebase and implement blindbit-oracle StreamBlockBatchSlim streaming to audit blocks

for each step in the plan provid me with a list of actions and wait for confirmation or edits before continuing

let me know if you have any questions or need clarification along the way

speed is not important, precision is valued