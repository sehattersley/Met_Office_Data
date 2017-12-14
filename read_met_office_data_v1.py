#!/usr/bin/python
# Aurthor: sehattersley
# Purpose: Read local weather data from Met Office Data Point and post it to emoncms
# Notes: Run this script as a cron job every 3 hours to match Met Office update frequency



# --- Imports ---
import metoffer # Used for reading data from Met Office Data Point. Info on metoffer data: https://pypi.python.org/pypi/MetOffer/
from math import sin, cos, sqrt, atan2, radians # Used to calculate the distance between two latitude and londitude points
import urllib # Used for web access
try:
	import httplib # Used for web access. Python 2
except ImportError:
	import http.client as httplib # Used for web access. Python 3
import datetime # Used for sun rise times etc
from astral import Astral # Used for sun rise times etc


# --- Initialise ---
sMetApiKey = 'enter API key here'
sLocation = 'London'
dLatitude = 51.508
dLongitude = -0.125



# --- Control Settings ---
bDebugPrint = 0 # Show debugging print statements
bDebugSendData = 1 # Send data to emoncms
bEmoncmsOther = 1
bEmoncmsOrg = 1



# --- Functions ---
def DistanceBetweenPoints(dLatitudeA, dLongitudeA, dLatitudeB, dLongitudeB):
	# Function to calculate the distance bewteen two points in km.
	#Note that this function required the following imports: from math import sin, cos, sqrt, atan2, radians
	dEarthRadius_km = 6373.0 # Approximate radius of earth in km
	dChangeInLongitude = dLongitudeB - dLongitudeA
	dChangeInLatitude = dLatitudeB - dLatitudeA
	a = sin(radians(dChangeInLatitude) / 2)**2 + cos(radians(dLatitudeA)) * cos(radians(dLatitudeB)) * sin(radians(dChangeInLongitude) / 2)**2
	c = 2 * atan2(sqrt(a), sqrt(1 - a))
	dDistanceBetweenPoints_km = round(dEarthRadius_km * c, 2)
	return dDistanceBetweenPoints_km

def CompassToDegrees(sCompass): # Function to convert compass direction into degrees
	dicCompassDirections = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
	dCompassDegrees = dicCompassDirections[sCompass]
	return dCompassDegrees

def PostToEmoncms(sSensorValueType, dSensorValue, conn, sLocation, ApiKey, sNodeID, bDebugPrint): # Function to post data to an emoncms server
	MeasuredData = (sSensorValueType + ":%.2f" %(dSensorValue)) #Data name cannot have spaces.
	Request = sLocation + ApiKey + "&node=" + sNodeID + "&json=" + MeasuredData
	conn.request("GET", Request) # Make a GET request to the emoncms data. This basically sends the data.
	Response = conn.getresponse() # Get status and error message back from webpage. This must be done before a new GET command can be done.
	Response.read() # This line prevents the error response not ready. Its to do with the http socket being closed.
	if bDebugPrint == 1:
		print(sSensorValueType + ": data post status and reason - " + str(Response.status) + ", " + str(Response.reason))



# --- Classes ---
class MetOfficeData(object): # Class for the CT and VT sensors
	def __init__(self, sLocation, dLatitude, dLongitude, sMetApiKey, sMeasurementType): # This is run when an onject is first created
		self.sLocation = sLocation
		self.dLatitude = dLatitude
		self.dLongitude = dLongitude
		self.sMetApiKey = sMetApiKey
		self.sMeasurementType = sMeasurementType
		
		oMet = metoffer.MetOffer(sMetApiKey)
		
		if self.sMeasurementType == 'nearest_loc_obs':
			self.dicWeatherData = oMet.nearest_loc_obs(self.dLatitude, self.dLongitude) # This finds the nearest observation station of which there are not that many so your data may be inaccruate.
		if self.sMeasurementType == 'nearest_loc_forecast':
			self.dicWeatherData = oMet.nearest_loc_forecast(dLatitude, dLongitude, metoffer.THREE_HOURLY) # This gives forecast data for the given area.

		self.oWeatherReport = metoffer.parse_val(self.dicWeatherData)

	def ReadData(self):
		# Get sun rise and set times etc
		oAstral = Astral() # Create object
		sCity = oAstral['London']
		#sun = sCity.sun(date=datetime.date(2017, 5, 11), local=True)
		sun = sCity.sun(date=datetime.datetime.now(), local=True)
		self.dDawn = float((str(sun['dawn'])[11:16]).replace(':', '.'))# Get dawn time, also only give charters 11 to 16. Replace : with . and convert to float.
		self.dSunRise = float((str(sun['sunrise'])[11:16]).replace(':', '.')) 
		self.dNoon = float((str(sun['noon'])[11:16]).replace(':', '.'))
		self.dSunSet = float((str(sun['sunset'])[11:16]).replace(':', '.'))
		self.dDusk = float((str(sun['dusk'])[11:16]).replace(':', '.'))
		if bDebugPrint == 1:
			print('Sun times for: ' + str(sCity))
			print('Latitude: %.02f; Longitude: %.02f\n' %(sCity.latitude, sCity.longitude))
			print('Dawn: ' + str(self.dDawn))
			print('Sunrise: ' + str(self.dSunRise))
			print('Noon: ' + str(self.dNoon))
			print('Sunset: ' + str(self.dSunSet))
			print('Dusk: ' + str(self.dDusk))
			print('')
		
		
		# Decide what time step to use
		if self.sMeasurementType == 'nearest_loc_obs':
			self.nTimeStep = len(self.oWeatherReport.data)-1 # Last item is the latest observation data i.e. current time (list starts at 0 not 1 so need to subtract 1). I think each increment is 1 hour for observation data
		if self.sMeasurementType == 'nearest_loc_forecast':
			self.nTimeStep = 2 # Each data item increments the time by 3 hours for forecast data. 2 seems to represent close to real time forecast.
		self.dicWeatherData = self.oWeatherReport.data[self.nTimeStep] 
		
		# Items common to both Measurement Types
		self.sTimeStamp = self.dicWeatherData['timestamp'][0]
		self.dElevation_m = self.oWeatherReport.elevation
		self.dTemperature_C = self.dicWeatherData['Temperature'][0]
		self.dHumidity_P = self.dicWeatherData['Screen Relative Humidity'][0]
		self.dWindSpeed_mph = self.dicWeatherData['Wind Speed'][0]
		self.sWindDirection = self.dicWeatherData['Wind Direction'][0]
		self.dWindDirection = CompassToDegrees(self.sWindDirection) # Convert wind direction to degrees
		self.nWeatherTypeID = self.dicWeatherData['Weather Type'][0]
		self.sWeatherType = metoffer.WEATHER_CODES[self.nWeatherTypeID] # Lookup the type of weather from the metoffer module based on the weather ID.
		self.sWeatherType, sSeparator, sEndText = self.sWeatherType.partition('(') # Remove the last bit of text which is in brackets. eg (night)
				
		if self.sMeasurementType == 'nearest_loc_obs': # Items unique to nearest_loc_obs
			self.sNearestLocation = self.oWeatherReport.name
			self.dNearestLatitude = self.oWeatherReport.lat
			self.dNearestLongitude = self.oWeatherReport.lon
			self.dDistanceToStation_km = DistanceBetweenPoints(self.dLatitude, self.dLongitude, self.dNearestLatitude, self.dNearestLongitude) # Function to give distance between two points
			self.dDewPoint_C = self.dicWeatherData['Dew Point'][0]
			self.dPressure_hPa = self.dicWeatherData['Pressure'][0]
			self.sPressureTendency = self.dicWeatherData['Pressure Tendency'][0]
			if self.sPressureTendency == 'R':
				self.sPressureTendency = 'Rise -> Better Weather'
			if self.sPressureTendency == 'F':
				self.sPressureTendency = 'Fall -> Worst Weather'		
			self.dVisibility_m = self.dicWeatherData['Visibility'][0] # For some reason the visiility is returned as a number rather than an ID. I think this is a Met Office error.
			
		if self.sMeasurementType == 'nearest_loc_forecast': # Items unique to nearest_loc_forecast
			self.dFeelTemperature_C = self.dicWeatherData['Feels Like Temperature'][0]
			self.dWindGust_mph = self.dicWeatherData['Wind Gust'][0]
			self.dPrecipitationProbability_P = self.dicWeatherData['Precipitation Probability'][0]
			self.nMaxUVIndex = self.dicWeatherData['Max UV Index'][0]
			self.sUVGuideance = metoffer.guidance_UV(self.nMaxUVIndex) # Function to return the Met Office guideance on UV exposure
			self.dVisibilityID = self.dicWeatherData['Visibility'][0]
			self.sVisibility = metoffer.VISIBILITY[self.dVisibilityID] # Function to return visibility description


	def PrintData(self):
		print('Weather data for: ' + self.sLocation + ' @ Latitude:' + str(self.dLatitude) + ', Longitude:' + str(self.dLongitude))
		if self.sMeasurementType == 'nearest_loc_obs':
			print('Nearest observation station: ' + self.sNearestLocation + ' @ Latitude: ' + str(self.dNearestLatitude) + ', Longitude: ' + str(self.dNearestLongitude))
			print("Distance to nearest observation station:", str(self.dDistanceToStation_km) + ' km')
		print(' ')
		
		print('RAW WEATHER DATA: Using ' + self.sMeasurementType)
		print('Number of time steps: ' + str(len(self.oWeatherReport.data)))
		print('Chosen time step: ' + str(self.nTimeStep))
		print(self.dicWeatherData) # Whole dictionary for the given time step. Note time stamp is given in the format: year, month, day, hour, minute.
		print(' ')

		print('INDIVIDUAL VALUES:')
		print('Time Stamp: ' + str(self.sTimeStamp))
		print('Elevation: ' + str(self.dElevation_m) + ' m')
		print('Weather Type: ' + self.sWeatherType)
		print('Temperature: ' + str(self.dTemperature_C) + '*C')
		print('Humidity: ' + str(self.dHumidity_P) + ' %')
		print('Wind Speed: ' + str(self.dWindSpeed_mph) + ' mph')
		print('Wind Direction: ' + self.sWindDirection + ' (' + str(self.dWindDirection) + ' *)')
		
		if self.sMeasurementType == 'nearest_loc_obs': # Items unique to nearest_loc_obs
			print('Dew Point: ' + str(self.dDewPoint_C) + ' *C')
			print('Pressure: ' + str(self.dPressure_hPa) + ' hpa')
			print('Pressure Tendency: ' + self.sPressureTendency)
			print('Visibility: ' + str(self.dVisibility_m) + ' m')
			
		if self.sMeasurementType == 'nearest_loc_forecast': # Items unique to nearest_loc_forecast
			print('Wind Gust Speed: ' + str(self.dWindGust_mph) + ' mph')
			print('Feels Like Temperature: ' + str(self.dFeelTemperature_C) +' *C')
			print('Precipitation Probability: ' + str(self.dPrecipitationProbability_P) + ' %')
			print('UV Exposure Guideance: ' + self.sUVGuideance)
			print('Visibility: ' + self.sVisibility)

		print(' ')



# --- Main Code ---

# The nearest observation station is too far away from my home so dont use this data.
# Read actual data from the nearest observation station
#oNearObs = MetOfficeData(sLocation, dLatitude, dLongitude, sMetApiKey, 'nearest_loc_obs') # Create an object
#oNearObs.ReadData() # Read the weather data for the object
#if bDebugPrint  == 1:
#	oNearObs.PrintData() # Print the data

# Read forecast data for the local area
oLocalForecast = MetOfficeData(sLocation, dLatitude, dLongitude, sMetApiKey, 'nearest_loc_forecast')
oLocalForecast.ReadData()
if bDebugPrint  == 1:
	oLocalForecast.PrintData()


# Send data to local emoncms server
if bDebugSendData == 1 and bEmoncmsOther == 1:
	sMyApiKey = "enter API key here" # My Linux server emoncms read & write api key
	Connection = httplib.HTTPConnection("localhost:80") # Address of local emoncms server with port number
	sLocation = "/emoncms/input/post?apikey=" # Subfolder for the given emoncms server
	sNodeID = "MetOffice" # Node IDs cant have any spaces

	PostToEmoncms("LocalForecastTemperature_C", oLocalForecast.dTemperature_C, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastFeelTemperature_C", oLocalForecast.dFeelTemperature_C, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastHumidity_P", oLocalForecast.dHumidity_P, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindSpeed_mph", oLocalForecast.dWindSpeed_mph, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindDirection_D", oLocalForecast.dWindDirection, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindGusts_mph", oLocalForecast.dWindGust_mph, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastPrecipitationProbability_P", oLocalForecast.dPrecipitationProbability_P, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("DawnTime_24", oLocalForecast.dDawn, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("SunRiseTime_24", oLocalForecast.dSunRise, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("NoonTime_24", oLocalForecast.dNoon, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("SunSetTime_24", oLocalForecast.dSunSet, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("DuskTime_24", oLocalForecast.dDusk, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)

# Send data to emoncms.org
if bDebugSendData == 1 and bEmoncmsOrg == 1:
	sMyApiKey = "enter API key here" # My emoncms.org read & write api key
	Connection = httplib.HTTPConnection("emoncms.org:80") # Address of emoncms server with port number
	sLocation = "/input/post?apikey=" # Subfolder for the given emoncms server
	sNodeID = "MetOffice" # Node IDs cant have spaces in them
	
	PostToEmoncms("LocalForecastTemperature_C", oLocalForecast.dTemperature_C, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastFeelTemperature_C", oLocalForecast.dFeelTemperature_C, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastHumidity_P", oLocalForecast.dHumidity_P, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindSpeed_mph", oLocalForecast.dWindSpeed_mph, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindDirection_D", oLocalForecast.dWindDirection, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastWindGusts_mph", oLocalForecast.dWindGust_mph, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("LocalForecastPrecipitationProbability_P", oLocalForecast.dPrecipitationProbability_P, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("DawnTime_24", oLocalForecast.dDawn, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("SunRiseTime_24", oLocalForecast.dSunRise, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("NoonTime_24", oLocalForecast.dNoon, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("SunSetTime_24", oLocalForecast.dSunSet, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)
	PostToEmoncms("DuskTime_24", oLocalForecast.dDusk, Connection, sLocation, sMyApiKey, sNodeID, bDebugPrint)



if bDebugPrint == 1:
	print('End of script')