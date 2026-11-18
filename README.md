# Response to Provincial Health Data Centre - Data Engineer Challenge

## Challenge Part 0 - Exploring the Data

- A fork of the main branch for the data-competency-assessment repository was made to my personal GitHub to ensure that I have a safe backup to revert to should issues arise

- The initial steps for this section was to open the URL in my most commonly used browser, in this case Chrome, which led me to the City of Cape Town Open Data Portal for service requests. 

- While some context was provided for what to expect, examining the data that was presented provides a better understanding of what I am working with. 

## Challenge Part 1
### Working out the API Endpoints

- There were 2 approaches I implemented to assertaining the API end points from this URL. 

1. The first apprach is to open the broswers developer tools in this case ```Ctrl + Shift + I``` in Chrome.
2. Scroll over to the **Network** tab
3. Click the **Fetch/ XHR** button and refresh the page which would provide me with a list all the HTTP requests that occured when the page was loaded.
4.  With the **Fetch/XHR** filter applied, I cleared the Network tab and reloaded the data view, then watched which requests fired as new data appeared. 
5. Inspecting each request's **Headers** tab showed that most calls (`self`, `settings`, `groups`, `datasets`, `metadata.xml`) only return the settings or metadata which follows standard query convention. 
6. The `FeatureServer` request was the one serving the data the frontend displays, which made it the main route to pull from.
7. Data can then be queried directly from the layer's `/query` endpoint
8. Setting the URL the API endpoint to `https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/Service_Requests_2023_until_20_May_2026/FeatureServer/` brngs me in contact with ArcGIS REST Services page which allows me to query data accordingly.
9. `...FeatureServer/query?where1=1&outFields=*&/f=json` results in the following:
  - `where1=1` return all the records
  - `&` acts as a concatenating feature
  - `outFields=*` returns all the related attribute fields
  - `f=json` sets the format for the outputted response
10. Due to the large quantity of data (5 million+) the output dataset will be capped accordingly at the `maxRecordCount` and will end up being retrieved in pages.
11. Confirmation of this was conducted by pasting the main route into the broswer afterwhich the additional query parameters (which occur after the `?`) were included for additional testing.

- The second approach involved using the frontend interface - This approach is not always available so the first one is usually standard.
1. On the dataset page, click **View Full Details** in the left-hand navigation panel.

2. This opens the dataset's **About** page (the URL now ends in `/about`). Scroll down to the **View API Resources** card on the right hand side of the page, which lists ready-made endpoints for each response format (e.g. GeoService, GeoJSON).

### Inspecting the dataset's schema

1. Using the same Network-tab approach as above, I inspected the `layers` request (`<FeatureServer URL>/layers?f=json`). This endpoint returns every layer in the service along with any associated tables.
2. 2. Opening this request URL directly in a browser tab returns the same JSON response, showing the fields for each layer and table in the service.
3. This is the list of records within the Fields:
  - Sub_Council (type: esriFieldTypeString, alias: Sub Council, SQL Type: sqlTypeNVarchar, length: 4000, nullable: true, editable: true)
  - Ward (type: esriFieldTypeString, alias: Ward, SQL Type: sqlTypeNVarchar, length: 256, nullable: true, editable: true)
  - Suburb (type: esriFieldTypeString, alias: Suburb, SQL Type: sqlTypeNVarchar, length: 4000, nullable: true, editable: true)
  - C3_Complaint_Type (type: esriFieldTypeString, alias: C3 Complaint Type, SQL Type: sqlTypeNVarchar, length: 4000, nullable: true, editable: true)
  - Work_Center (type: esriFieldTypeString, alias: Work Center, SQL Type: sqlTypeNVarchar, length: 4000, nullable: true, editable: true)
  - Notification (type: esriFieldTypeInteger, alias: Notification, SQL Type: sqlTypeInteger, nullable: true, editable: true)
  - Notification_type (type: esriFieldTypeString, alias: Notification type, SQL Type: sqlTypeNVarchar, length: 4000, nullable: true, editable: true)
  - X_Y_Co_ordinate_1 (type: esriFieldTypeDouble, alias: X-Y Co ordinate 1, SQL Type: sqlTypeFloat, nullable: true, editable: true)
  - X_Y_Co_ordinate_2 (type: esriFieldTypeDouble, alias: X-Y Co ordinate 2, SQL Type: sqlTypeFloat, nullable: true, editable: true)
  - Created_On_Date (type: esriFieldTypeDate, alias: Created On Date, SQL Type: sqlTypeTimestamp2, length: 8, nullable: true, editable: true)
  - Changed_on (type: esriFieldTypeDate, alias: Changed on, SQL Type: sqlTypeTimestamp2, length: 8, nullable: true, editable: true)
  - Completed_Date (type: esriFieldTypeDate, alias: Completed Date, SQL Type: sqlTypeTimestamp2, length: 8, nullable: true, editable: true)
  - Notifications_Created (type: esriFieldTypeInteger, alias: Notifications Created, SQL Type: sqlTypeInteger, nullable: true, editable: true)
  - ObjectId (type: esriFieldTypeOID, alias: ObjectId, SQL Type: sqlTypeInteger, length: 0, nullable: false, editable: false)

### Inspecting the dataset's schema

