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
		self.MAX_RECONNECT_ATTEMPTS = 5
		
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
		print comms_success, completed
		
		comms_success, completed, data_buffer = self.spoolData()
		print comms_success, data_buffer
	
	def spoolData(self):
		completed = False
		comms_success = False
		data_buffer = ''
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			comms_success, response = self.arduino.Call('TX', 1)
			if not comms_success:
				return comms_success, completed, data_buffer	
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if crc_success == True:
				if ((reply != 'fl') and (reply != 'to')):							# TX command arrived and data frame successfully returned.
					data_buffer += reply
					tries = 0
					outgoing_command = 'AK'
					while ((completed == False) and (tries < self.MAX_PARAMETER_RETRIES)):
						comms_success, response = self.arduino.Call(outgoing_command, 1)
						if not comms_success:
							return comms_success, completed, data_buffer	
						print response						
						reply = response[0][1]
						crc_success = response[0][0]
						if crc_success == True:
							if reply == 'cr':										# Arduino has asked if we want this data frame reset.
								outgoing_command = 'AR'
								tries += 1
							elif reply == 'fs':										# Arduino has signalled that it is finished, need to ask for confirmation.
								outgoing_command = 'CC'
							elif reply == 'cc':										# Arduino has confirmed TX completion.
								completed = True
							elif reply == 'to':										# Arduino sent timeout. Send TX command again.
								tries = 0
								break
							else:													# Next data frame arrived.
								data_buffer += reply
								outgoing_command = 'AK'
						elif crc_success == False:									# Reply arrived garbled, ask for data frame to be resent.
							outgoing_command = 'AR'
							tries += 1
				else:																# Arduino sent failed to understand command or sent timeout ('to'). Send TX command again.
					tries += 1
			elif crc_success == False:												# First reply arrived garbled so unsure if arduino is spooling.
				tries += 1															# Send TX command again.
		return comms_success, completed, data_buffer
	
	def setTime(self):
		completed = False
		comms_success = False
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			# Connect to a NTP server and query the current time
			got_timestamp, timestamp = self.getNtpTime()
			if got_timestamp == False:
				print 'Unable to obtain NTP timestamp.'
				break
			print timestamp
			comms_success, response = self.arduino.Call('ST', 1)
			if not comms_success:
				return comms_success, completed
			print response
			reply = response[0][1]
			crc_success = response[0][0]
			if ((reply == 'ak') and (crc_success == True)):
				time_headers = ['YY', 'MM', 'DD', 'hh', 'mm', 'ss']
				for i, parameter in enumerate(timestamp):
					tries = 0
					while tries < self.MAX_PARAMETER_RETRIES:
						comms_success, response = self.arduino.Call(time_headers[i], 1)
						if not comms_success:
							return comms_success, completed
						print response
						reply = response[0][1]
						crc_success = response[0][0]
						if ((reply == 'ht') and (crc_success == True)):
							comms_success, response = self.arduino.Call(str(parameter), 1)
							if not comms_success:
								return comms_success, completed
							print response
							reply = response[0][1]
							crc_success = response[0][0]
							if ((reply == 'ts') and (crc_success == True)):
								completed = True
								break
							elif ((reply == 'ht') and (crc_success == True)):
								break
							elif ((reply == 'to') and (crc_success == True)):
								completed = False
								return comms_success, completed
							else:
								tries += 1
						else:
							tries += 1
			else:
				tries += 1
		return comms_success, completed
	
	def startComms(self):
		# Start the serial connection with the arduino.
		self.arduino = ArduinoComms.ArduinoComms(self.arduino_baud, self.arduino_port, self.arduino_timeout_secs, self.MAX_RECONNECT_ATTEMPTS)
	
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
	
