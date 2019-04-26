import serial
import time

class ArduinoComms():
	def __init__(self, baud, port, timeout_secs):
		self.baud = baud
		self.port = port
		self.timeout = timeout_secs
		self.ser = serial.Serial(self.port, self.baud)
	
	def __SerialSpeak(self, message):
		try:
			message = '>' + message + '\n'
		except:
			message = '>' + str(message) + '\n'
		print message
		for current_character in message:
			self.ser.write(current_character)
	
	def __SerialListen(self, timeout):
		timeout_start = time.time()
		returned_message = ''
		finished = False
		if timeout == 0.0:
			while finished == False:
				while ((self.ser.inWaiting() > 0)):
					received_character = self.ser.read()
					if received_character == '\n':
						finished = True
						break
					else:
						returned_message += received_character
		else:
			started = False
			while time.time() < timeout_start + timeout:
				received_character = self.ser.read()
				if received_character == '>':
					started = True
				elif received_character == '\n':
					if started == True:
						break
				else:
					if started == True:
						returned_message += received_character
		return returned_message
	
	def Call(self, message, expected_replies):
		self.ser.flushInput()
		self.__SerialSpeak(message)
		response = []
		for reply in range(expected_replies):
			temp = self.__SerialListen(self.timeout)
			response.append(temp)
		return response
		
