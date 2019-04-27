import urllib
import ntplib
from time import ctime
import datetime
import time

import ArduinoComms

class AQMeshStation():
	def __init__ (self):
		self.MAX_COMMAND_RETRIES = 10
		self.MAX_PARAMETER_RETRIES = 5
		self.MAX_TIMESERVER_RETRIES = 5
		
		self.arduino_port = '/dev/ttyACM0'
		self.arduino_baud = 115200
		self.arduino_timeout_secs = 1.0
		
		# Block until we detect a working web connection.
		while (not self.internetOn()):
			pass
		
		# Start the serial connection with the arduino.
		comms_success = self.startComms()
		
		# Set the time on the arduino RTC to that returned from the NTP server.
		comms_success, completed = self.setTime()
		print completed
	
	def setTime(self):
		completed = False
		# Check if serial connection to arduino is still open.
		try:
			self.arduino.ser.isOpen()
			comms_success = True
		except:
			# If not, setTime fails.
			print 'Could not open serial connection with Arduino...'
			comms_success = False
			return comms_success, completed
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			# Connect to a NTP server and query the current time
			got_timestamp, timestamp = self.getNtpTime()
			if got_timestamp == False:
				print 'Unable to obtain NTP timestamp.'
				break
			print timestamp
			response = self.arduino.Call('ST', 1)
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if ((reply == 'ak') and (crc_success == True)):
				time_headers = ['YY', 'MM', 'DD', 'hh', 'mm', 'ss']
				for i, parameter in enumerate(timestamp):
					tries = 0
					while tries < self.MAX_PARAMETER_RETRIES:
						response = self.arduino.Call(time_headers[i], 1)
						print response
						reply = response[0][1]
						crc_success = response[0][0]
						if ((reply == 'ht') and (crc_success == True)):
							response = self.arduino.Call(str(parameter), 1)
							print response
							reply = response[0][1]
							crc_success = response[0][0]
							if ((reply == 'TS') and (crc_success == True)):
								completed = True
								break
							elif ((reply == 'ht') and (crc_success == True)):
								break
							else:
								tries += 1
						else:
							tries += 1
			else:
				tries += 1
		return comms_success, completed
	
	def startComms(self):
		# Start the serial connection with the arduino.
		try:
			self.arduino = ArduinoComms.ArduinoComms(self.arduino_baud, self.arduino_port, self.arduino_timeout_secs)
			time.sleep(1.0)
			return True
		except:
			return False
	
	def calculateLRC(self, parameter_string):
		# Calculate a simple left-to-right xor checksum of the parameter value as received.
		lrc = 0;
		for current_character in parameter_string:
			lrc = lrc ^ ord(current_character)
		return lrc
	
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
		tries = 0
		completed = False
		while((tries < self.MAX_TIMESERVER_RETRIES) and (completed == False)):
			try:
				response = c.request('europe.pool.ntp.org', version = 3)
				print 'NTP timestamp obtained from europe.pool.ntp.org'
				completed = True
			except:
				print 'No response received from europe.pool.ntp.org.'
				tries += 1
		
		datetime_string = ctime(response.tx_time)
		datetime_object = datetime.datetime.strptime(datetime_string, '%a %b %d %H:%M:%S %Y')
		# Want to have output in the following format (all ints): YEAR MONTH DAY HRS MINS SECS
		year = datetime_object.year
		month = datetime_object.month
		day = datetime_object.day
		hour = datetime_object.hour
		minute = datetime_object.minute
		second = datetime_object.second
		return completed, [year, month, day, hour, minute, second]

if __name__ == '__main__':
	aqmeshstation = AQMeshStation()
	
