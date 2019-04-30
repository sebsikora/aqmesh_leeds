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
		
		self.ARDUINO_PORT = '/dev/ttyACM0'
		self.ARDUINO_BAUD = 115200
		self.ARDUINO_TIMEOUT_SECS = 1.0
		
		self.STATION_ID = 0
		self.FTP_SERVER = 'ftpupload.net'
		self.FTP_PORT = 21
		self.FTP_LOGIN = 'epiz_23835097'
		self.FTP_PASSWORD = 'YRyhrbvxTU3bBK'
		self.FTP_ROOT_DIR = '/htdocs/'
		
		self.NTP_TIMESERVER = 'europe.pool.ntp.org'
		self.WEB_CONNECTIVITY_CHECK_URL = 'http://www.google.com'
		
		self.LOCAL_DEFAULT_PATH = './local_store/'
		
		# Block until we detect a working web connection.
		while (not self.internetOn()):
			pass
		
		# Start the serial connection with the arduino.
		comms_success = self.startComms()
		
		# Set the time on the arduino RTC to that returned from the NTP server.
		comms_success, completed = self.setTime()
		print comms_success, completed
		
		logging_interval_secs = 30
		number_of_logs = 10
		
		start_timestamp = time.time()
		for i in range(number_of_logs):
			time_to_upload = False
			while (time_to_upload == False):
				timestamp = time.time()
				print str(logging_interval_secs - int(timestamp - start_timestamp)) + ' seconds until next update...'
				if int(timestamp - start_timestamp) >= logging_interval_secs:
					time_to_upload = True
				time.sleep(1.0)
			start_timestamp = time.time()
			print 'Updating...'
			
			comms_success, completed, data_buffer = self.spoolData()
			new_index = int(data_buffer[0:3])
			data_buffer = data_buffer[4:]
			print ""
			print new_index
			print data_buffer
			
			# Block until we detect a working web connection.
			while (not self.internetOn()):
				pass
			
			if comms_success:
				print 'Storing received data locally...'
				local_file_path = self.storeData(self.LOCAL_DEFAULT_PATH, data_buffer, new_index)
				print 'Uplodaing received data to FTP server...'
				destination_dir = self.FTP_ROOT_DIR + 'station-' + str(self.STATION_ID)
				upload_success = self.uploadData(self.FTP_SERVER, self.FTP_PORT, self.FTP_LOGIN, self.FTP_PASSWORD, destination_dir, local_file_path)
			
	def uploadData(self, ftp_server, ftp_port, ftp_login, ftp_password, destination_dir, local_file_path):
		from ftplib import FTP
		import os
		upload_successful = False
		print '-------------------------------- FTP debug info --------------------------------'
		try:
			ftp = FTP()
			ftp.set_debuglevel(2)
			ftp.connect(ftp_server, ftp_port)
			ftp.login(ftp_login, ftp_password)
			try:
				ftp.cwd(destination_dir)
			except:
				ftp.mkd(destination_dir)
				ftp.cwd(destination_dir)
			file = open(local_file_path, 'rb')
			ftp.storbinary('STOR %s' % os.path.basename(local_file_path), file, 1024)
			file.close()
			print '--------------------------------------------------------------------------------'
			print 'Uplodad to FTP server completed.'
			print '--------------------------------------------------------------------------------'
			upload_successful = True
		except:
			print 'Unable to upload data to FTP server.'
			print '--------------------------------------------------------------------------------'
			upload_successful = False
		return upload_successful
	
	def storeData(self, dir_path, data_buffer, new_index):
		import os
		import datetime
		directory_exists = os.path.isdir(dir_path)						# Check if local store directory exists.
		if not directory_exists:										# If not, create it.
			os.mkdir(dir_path)	
		todays_date = datetime.date.today()								# Get todays date in YYYYMMDD format.
		year = str(todays_date.year)
		month = str(todays_date.month).zfill(2)
		day = str(todays_date.day).zfill(2)
		date_string = year + month + day
		#~ # Get a list of all files in the local store.
		#~ files_in_directory = [f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))]
		#~ # Identify todays log files (start with todays date in YYYYMMDD format and contain the station ID no.
		#~ todays_data_files = [f for f in files_in_directory if ((f.split('_')[0].startswith(date_string)) and (f.split('_')[-1].startswith('station-' + str(self.STATION_ID))))]
		#~ todays_data_file_indices = [int(i.split('.')[-1]) for i in todays_data_files]
		#~ if todays_data_files:											# Determine the highest index of existing logs.
			#~ new_index = max(todays_data_file_indices) + 1				# Create a new filename with index incremented.
		#~ else:
			#~ new_index = 0
		new_index_string = str(new_index).zfill(3)
		new_filename = dir_path + date_string + '_station-' + str(self.STATION_ID) + '.' + new_index_string
		if os.path.isfile(new_filename):
			j = 0
			while (j < 1000):
				if os.path.isfile(new_filename[:-4] + '_' + str(j).zfill(3) + new_filename[-4:]):
					j += 1
				else:
					new_filename = new_filename[:-4] + '_' + str(j).zfill(3) + new_filename[-4:]
					break
		with open(new_filename, 'a') as output_file:					# Create a new file with this filename.
			print new_filename											# Write contents of data buffer to this file.
			output_file.write(data_buffer)
		return new_filename												# Return the path to the new log.
	
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
			if ((crc_success == True) and (reply != 'to')):							# TX command arrived and file index string successfully returned.
				data_buffer = data_buffer + reply + '>'
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
				tries = 0
			elif ((crc_success == True) and (reply == 'to')):					# Arduino failed to understand command or sent timeout ('to'). Send TX command again.
				tries += 1
			elif crc_success == False:											# File index string reply arrived garbled so send TX command again to ask Arduino to repeat
				tries += 1
		return comms_success, completed, data_buffer
	
	def setTime(self):
		completed = False
		comms_success = False
		tries = 0
		while ((completed == False) and (tries < self.MAX_COMMAND_RETRIES)):
			# Connect to a NTP server and query the current time
			got_timestamp, timestamp = self.getNtpTime(self.NTP_TIMESERVER)
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
								break
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
					if not comms_success:
						break
					else:
						tries = 0
			else:
				tries += 1
		return comms_success, completed
	
	def startComms(self):
		# Start the serial connection with the arduino.
		self.arduino = ArduinoComms.ArduinoComms(self.ARDUINO_BAUD, self.ARDUINO_PORT, self.ARDUINO_TIMEOUT_SECS, self.MAX_RECONNECT_ATTEMPTS)
	
	def internetOn(self):
		print 'Checking for working internet connection...'
		try:
			urllib.urlopen(self.WEB_CONNECTIVITY_CHECK_URL)
			print 'Connection works!'
			return True
		except:
			print 'No internet connection available.'
			return False
	
	def getNtpTime(self, ntp_timeserver):
		print 'Grabbing time...'
		c = ntplib.NTPClient()
		tries = 0
		completed = False
		while((tries < self.MAX_TIMESERVER_RETRIES) and (completed == False)):
			try:
				response = c.request(ntp_timeserver, version = 3)
				print 'NTP timestamp obtained from ' + ntp_timeserver + ' .'
				completed = True
			except:
				print 'No response received from ' + ntp_timeserver + ' .'
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
	
