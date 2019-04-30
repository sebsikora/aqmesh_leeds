import serial
import time
import crcmod.predefined

class ArduinoComms():
	def __init__(self, baud, port, timeout_secs, max_reconnect_attempts):
		self.baud = baud
		self.port = port
		self.timeout = timeout_secs
		self.max_reconnect_attempts = max_reconnect_attempts
		self.connect()
	
	def connect(self):
		comms_success = False
		tries = 0
		while ((comms_success == False) and (tries < self.max_reconnect_attempts)):
			try:
				self.ser = serial.Serial(self.port, self.baud)
				comms_success = True
				time.sleep(1.0)
			except:
				comms_success = False
				tries += 1
				print 'No serial connection with Arduino...'
				time.sleep(0.05)
		return comms_success
	
	def __SerialSpeak(self, message):
		try:
			message = '>' + message + '<' + str(self.calcCRC8(message)) + '\0'
		except:
			message = '>' + str(message) + '<' + str(self.calcCRC8(str(message))) + '\0'
		print message
		for current_character in message:
			self.ser.write(current_character)
	
	def __SerialListen(self, timeout):
		returned_message = ''
		crc_check_string = ''
		crc_success = False
		mode = 0
		started = False
		finished = False
		if timeout == 0.0:
			while finished == False:
				while ((self.ser.inWaiting() > 0)):
					received_character = self.ser.read(1)
					if received_character == '>':
						started = True
						returned_message = ''
						mode = 0
					elif received_character == '<':
						mode = 1
					elif received_character == '\0':
						if started == True:
							finished = True
							break
					else:
						if mode == 0:
							returned_message += received_character
						elif mode == 1:
							crc_check_string += received_character
		else:
			mode = 0
			started = False
			timeout_start = time.time()
			while time.time() < timeout_start + timeout:
				if self.ser.inWaiting() > 0:
					received_character = self.ser.read(1)
					if received_character == '>':
						started = True
						returned_message = ''
						mode = 0
					elif received_character == '<':
						mode = 1
					elif received_character == '\0':
						if started == True:
							break
					else:
						if started == True:
							if mode == 0:
								returned_message += received_character
							elif mode == 1:
								crc_check_string += received_character
		try:
			crc_check_value = int(crc_check_string)
			message_crc_check_value = self.calcCRC8(returned_message)
			print 'CRC8 check', crc_check_value, message_crc_check_value
			if crc_check_value == message_crc_check_value:
				crc_success = True
		except:
			crc_success = False
		return crc_success, returned_message
	
	def Call(self, message, expected_replies):
		comms_success = False
		while (self.ser.inWaiting() > 0):								# Clear the serial input buffer prior to beginning a call->response...
			self.ser.read(1)
		try:
			response = []
			self.__SerialSpeak(message)
			for reply in range(expected_replies):
				crc_success, reply_message = self.__SerialListen(self.timeout)
				response.append([crc_success, reply_message])
			comms_success = True
		except:
			comms_success = False
			response = [['', ''] for i in range(expected_replies)]
		return comms_success, response
	
	def calcCRC8(self, message):
		crc8 = crcmod.predefined.mkPredefinedCrcFun('crc-8-maxim')
		crc8_check_value = crc8(message)
		return crc8_check_value
		
		
