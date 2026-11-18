# Response to Provincial Health Data Centre - Data Engineer Challenge

## Challenge Part 0 - Exploring the Data

- A fork of the main branch for the data-competency-assessment repository was made to my personal GitHub to ensure that I have a safe backup to revert to should issues arise

- The initial steps for this section was to open the URL in my most commonly used browser, in this case Chrome, which led me to the City of Cape Town Open Data Portal for service requests. 

- While some context was provided for what to expect, examining the data that was presented provides a better understanding of what I am working with. 

## Challenge Part 1 - Working out the API Endpoints

- There were 2 approaches I implemented to assertaining the API end points from this URL. 
1. The first apprach is to open the broswers developer tools in this case ```Ctrl + Shift + I``` in Chrome.
2. Scroll over to the **Network** tab
3. Click the **Fetch/ XHR** button and refresh the page which would provide me with a list all the HTTP requests that occured when the page was loaded.
4.  With the **Fetch/XHR** filter applied, I cleared the Network tab and reloaded the data view, then watched which requests fired as new data appeared. 
5. Inspecting each request's **Headers** tab showed that most calls (`self`, `settings`, `groups`, `datasets`, `metadata.xml`) only return the settings or metadata which follows standard query convention. 
6. The `FeatureServer` request was the one serving the data the frontend displays, which made it the main route to pull from.

