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