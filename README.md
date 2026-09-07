FOR BUSES.
cd into buses directory.
You will then need two things:

1. a .env file with a single line APIKEY=yourapikey which you get from https://opendata.transport.nsw.gov.au/ and making an account and going to your profile and creating an api key.
2. a mysql server with a database called buses. change the values in functions.py to point to your server. Local docker server is easiest.

Once those are done, you can run bash initialise.sh and it will run all the setup scripts.

Then run main.py and keep that running for however long you want. It constantly gets realtime data and saves it as historical so if you want data for the past month, you will have to keep it running for a month and all of the aggregated data will be there in the database for the last month.

If you every stop main.py it's fine there will be some missing data for the time that was missed but the program will work fine.
