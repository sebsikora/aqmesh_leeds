import urllib
import ntplib
from time import ctime
import datetime

import ArduinoComms

class AQMeshStation():
	def __init__ (self):
		self.MAX_COMMAND_RETRIES = 5
		
		# Block until we detect a working web connection.
		while (not self.internetOn()):
			pass
		
		# Connect to a NTP server and query the current time
		timestamp = self.getNtpTime()
		print timestamp
		
		# Start the serial connection with the arduino.
		self.arduino = ArduinoComms.ArduinoComms(57600, '/dev/ttyACM0', 0.5)
		
		# Set the time on the arduino RTC to that returned from the NTP server.
		self.setTime(timestamp)
	
	def setTime(self, timestamp):
		response = ['']
		tries = 0
		while ((response[0] != 'ack') and (tries < self.MAX_COMMAND_RETRIES)):
			response = self.arduino.Call('Settime', 1)
			tries += 1
			print response
		
		# ----------- Simulating comms glitch, command is sent again when arduino expects a time header ------------------
		# Send the erroneous command...
		print self.arduino.Call('Settime', 1)
		response = ['']
		# The arduino should have switched back to command mode - try sending the command again...
		while ((response[0] != 'ack') and (tries < self.MAX_COMMAND_RETRIES)):
			response = self.arduino.Call('Settime', 1)
			tries += 1
			print response
		# ----------------------------------------------------------------------------------------------------------------
		
		time_headers = ['YY', 'MM', 'DD', 'hh', 'mm', 'ss']
		completed = False
		for i, parameter in enumerate(timestamp):
			response = ['']
			tries = 0
			while ((response[0] != 'hit') and (tries < self.MAX_COMMAND_RETRIES)):
				response = self.arduino.Call(time_headers[i], 1)
				tries += 1
				print response
			
			#~ # ----------- Simulating comms glitch, time header is sent again when arduino expects a time value -------------
			#~ if i == 0:
				#~ # Send the erroneous header...
				#~ print self.arduino.Call('YY', 1)
				#~ response = ['']
				#~ # The arduino should have switched back to header mode - try sending the header again...
				#~ while ((response[0] != 'hit') and (tries < self.MAX_COMMAND_RETRIES)):
					#~ response = self.arduino.Call('YY', 1)
					#~ tries += 1
					#~ print response
			#~ # --------------------------------------------------------------------------------------------------------------
			
			response = ['']
			tries = 0
			while ((response[0] != 'hit') and (tries < self.MAX_COMMAND_RETRIES)):
				response = self.arduino.Call(str(parameter), 1)
				tries += 1
				print response
				if response[0] == 'Time set.':
					completed = True
					break
			if completed == True:
				break
	
	def internetOn(self):
		print 'Checking for working internet connection...'
		try:
			urllib.urlopen("http://www.google.com")
			print 'Connection works!'
			return True
		except:
			print 'No internet connection available.'
			return False
	
	def getNtpTime(self):
		print 'Grabbing time...'
		c = ntplib.NTPClient()
		
		while(True):
			try:
				response = c.request('europe.pool.ntp.org', version = 3)
				print 'Time obtained from europe.pool.ntp.org'
				break
			except:
				print 'No response received from europe.pool.ntp.org.'
		
		datetime_string = ctime(response.tx_time)
		datetime_object = datetime.datetime.strptime(datetime_string, '%a %b %d %H:%M:%S %Y')
		# Want to have output in the following format (all ints): YEAR MONTH DAY HRS MINS SECS
		year = datetime_object.year
		month = datetime_object.month
		day = datetime_object.day
		hour = datetime_object.hour
		minute = datetime_object.minute
		second = datetime_object.second
		return [year, month, day, hour, minute, second]

if __name__ == '__main__':
	aqmeshstation = AQMeshStation()
	
