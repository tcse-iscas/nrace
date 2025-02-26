from __future__ import print_function
import json
import os
import sys
import pprint
import time
import z3Scheduler
import Logging
import json
import re

logger=Logging.logger

def printDict (dict):
	'''print dict <dict> for debug'''
	#customize indent=4
	pp=pprint.PrettyPrinter(indent=4)
	pp.pprint(dict)
	pass

def printObj (obj):
	'''print object <Object> for debug'''
	#print '========object: ', obj
	#print 'details: ',  obj.__dict__
	#print 'items: 	', ','.join(['%s:%s' % item for item in obj.__dict__.items()])
	pass

def print_obj (obj, fieldList):

	res=list()
	for prop in obj.__dict__:
		if prop not in fieldList:
			continue
		#print  'prop is: %s (type: %s), obj.__dict__[prop] is: %s (type: %s)' %(prop, type(prop), obj.__dict__[prop], type(obj.__dict__[prop]))
		res.append(str(prop)+':'+str(obj.__dict__[prop]))
	return '{'+', '.join(res)+'}'
	pass

LogEntryType={
	"DECLARE":0,
	"WRITE":1,
	"PUTFIELD":2,
	"READ":10,
	"GETFIELD":11,
	"FUNCTION_ENTER":13,
	"FUNCTION_EXIT":14,
	"ASYNC_INIT":20,
	"ASYNC_BEFORE":21,
	"ASYNC_AFTER":22,
	"ASYNC_PROMISERESOLVE":23,
	"SCRIPT_ENTER":32,
	"SCRIPT_EXIT":33,
	"SOURCE_MAPPING":35,
	"FS_OPEN": 40,
	"FS_READ": 41,
	"FS_WRITE": 42,
	"FS_CLOSE": 43,
	"FS_DELETE": 44,
	"FS_CREATE": 45,
	"FS_STAT": 46,
	"INVOKE_FUN": 47,
	0:"DECLARE",
	1:"WRITE",
	2:"PUTFIELD",
	10:"READ",
	11:"GETFIELD",
	13:"FUNCTION_ENTER",
	14:"FUNCTION_EXIT",
	20:"ASYNC_INIT",
	21:"ASYNC_BEFORE",
	22:"ASYNC_AFTER",
	23:"PROMISERESOLVE",
	32:"SCRIPT_ENTER",
	33:"SCRIPT_EXIT",
	35:"SOURCE_MAPPING",
	40: "FS_OPEN",
	41:"FS_READ",
	42: "FS_WRITE",
	43: "FS_CLOSE",
	44: "FS_DELETE",
	45: "FS_CREATE",
	46: "FS_STAT",
	47: "INVOKE_FUN"
}

VarAccessType = {
	"READ":"R",
	"GETFIELD":"R",
	"WRITE":"W",
	"PUTFIELD":"W"
}

FileAccessType = {
	"FS_CREATE": "C",
	"FS_DELETE": "D",
	"FS_READ": "R",
	"FS_WRITE": "W",
	"FS_OPEN": "O",
	"FS_CLOSE": "X",
	"FS_STAT": "S"
}

_fsPattern = {
	"C": ["D", "R", "O", "S"],
	"D": ["C", "R", "W", "O", "X", "S"],
	"R": ["C", "D", "W"],
	"W": ["D", "R"],
	"O": ["C", "D", "X"],
	"X": ["D", "O"],
	"S": ["C", "D"]
}

def isFsRace (rcd1, rcd2):
	'''
	@param <DataAccessRecord>
	@return <Boolean>: to check whether rcd1 and rcd2 form an event race pair
	'''
	if rcd2.accessType in _fsPattern[rcd1.accessType]:
		return True
	else:
		return False
	pass

ResourcePriority={
	#FSEVENTWRAP, FSREQCALLBACK, GETADDRINFOREQWRAP, GETNAMEINFOREQWRAP, HTTPINCOMINGMESSAGE,
	#HTTPCLIENTREQUEST, JSSTREAM, PIPECONNECTWRAP, PIPEWRAP, PROCESSWRAP, QUERYWRAP,
	#SHUTDOWNWRAP, SIGNALWRAP, STATWATCHER, TCPCONNECTWRAP, TCPSERVERWRAP, TCPWRAP,
	#TTYWRAP, UDPSENDWRAP, UDPWRAP, WRITEWRAP, ZLIB, SSLCONNECTION, PBKDF2REQUEST,
	#RANDOMBYTESREQUEST, TLSWRAP, Microtask, Timeout, Immediate, TickObject
	
	#corresponding to the paper <sementics of asynchronous javascript>
	#TODO: promise
	'TickObject':0,
	'Immediate':1,
	#regard IMMEDIATE event and TIMEOUT event as same priority event
	'Timeout':2,
	'Other':3
}

def getPriority(resourceType):
	if(ResourcePriority.has_key(resourceType)):
		return ResourcePriority[resourceType]
	else:
		return ResourcePriority['Other']
	pass

class Reg_or_Resolve_Op:

	def __init__ (self, prior, follower, resourceType, lineno):
		self.prior = prior
		self.follower = follower
		self.resourceType = resourceType
		self.lineno = lineno
		pass

class Callback:

	def __init__ (self, asyncId, prior, resourceType, hbType, lineno):
		self.asyncId=asyncId
		self.prior=prior
		self.resourceType=resourceType
		self.priority=getPriority(resourceType)
		self.hbType=hbType
		self.register=lineno
		#save DataAccessRecord/FileAccessRecord/Reg_or_Resolve_Op into self.records
		self.records=list()
		self.postCbs=dict()
		#store the lineno of start, data accesses, registers, end
		#self.instructions=list()
		pass

	def addStart (self, lineno):
		self.start=lineno
		#self.addInstruction(lineno)
		pass

	def addEnd (self, lineno):
		self.end=lineno
		#self.addInstruction(lineno)
		pass
	
	def isOneAccessRecord (self):
		count = 0
		for rcd in self.records:
			if not isinstance(rcd, Reg_or_Resolve_Op):
				count += 1
		if count == 1:
			return True
		else:
			return False
		pass

	def addRecord (self, rcd):	
		
		#if rcd.lineno == '11758r':
			#print(print_obj(rcd, ['follower', 'prior', 'resourceType', 'lineno']))
		self.records.append(rcd.lineno)
		#because we use addRecord() to save Reg_or_Resolve instance, so it can have no attribute 'location'
		if isinstance(rcd, Reg_or_Resolve_Op):
			return
		#if len(self.records)==1:
		if self.isOneAccessRecord():
			self.location=rcd.location
		#self.addInstruction(rcd.lineno)
		'''		
		if self.asyncId == '16':
			print('++++++++++++++++++debug-addRecord:')
			print("records: %s" %(self.records))
			print("current lineno: %s" %(rcd.lineno))
		'''
		pass

	def getCbLoc (self):
		if hasattr(self, 'location'):
			return self.location
		else:
			return 0
		pass

	def addPostCb (self, postCb):
		if postCb.priority not in self.postCbs:
			self.postCbs[postCb.priority]=list()
		#self.postCbs.append(postCb.asyncId)
		self.postCbs[postCb.priority].append(postCb.asyncId)
		pass
	'''
	def addInstruction (self, lineno):
		self.instructions.append(lineno)
		pass
	'''

	def toJSON (self, file_name):
		try:
			with open(file_name, "a+") as f:
				json.dump(self, f, skipkeys = False, ensure_ascii = False, check_circular = True, allow_nan = True, cls = None, indent = True, separators = None, encoding = 'utf-8', default = None, sort_keys = False)
		except Exception, e:
			message = 'Write [%s...] to file [%s] error: json.dump error' %(str(self)[0:10], file_name)
			print ("%s\n\t%s" %(message, e.message))
			print ("e.message: %s" %(e.message))
			return False
		else:
			return True
		pass

class CbStack:

	def __init__ (self):
		self.stack=list()
		self.cbs=dict()
		#if the data access happens after the script exits and before enter a callback, allocate '0' to its eid
		#self.cbs['0'] = None
		#all data access records and file access records are stored in self.records property, indexed by lineno
		self.records=dict()
		self.vars=dict()
		#all file access records are stored in self.files property, indexed by file name, each file name corresponds to a list of lineno of FileAccessRecord
		self.files = dict()
		#save callback in initialized order
		self.cbForFile = list()
		#save all register and resolve instances
		self.rrdict = dict()
		self.testsuit = dict()
		self.test_case_count = 0
		self.cb_cache = list()
		self.script_count = 1
		pass
	
	def get_script_count (self):
		res = self.script_count
		self.script_count += 1
		return str(res) + '-'
		pass

	def add_in_cb_cache (self, asyncId):
		self.cb_cache.append(asyncId)
		pass

	def identify_test_case (self):
		case_id = self.test_case_count
		self.testsuit[case_id] = self.cb_cache
		self.cb_cache = list()
		self.test_case_count += 1
		pass
	
	def save_register_resolve (self, rr):
		self.rrdict[rr.lineno] = rr
		self.records[rr.lineno] = rr
		pass

	def top (self):
		#print '=====CbStack.top():====='
		#print self.stack
		if len(self.stack) > 0:
			return self.stack[len(self.stack)-1]
		else:
			#if the data access happens after the script exits and before enter a callback, allocate '0' to its eid
			return '0'
		pass

	def enter (self, cbAsyncId, lineno):
		self.stack.append(cbAsyncId)
		
		if cbAsyncId in self.cbs:
			self.cbs[cbAsyncId].addStart(lineno)
		'''
		instruction=StartandEndRecord(cbAsyncId, 'start', lineno)
		self.addDARecord(instruction)
		'''
		pass

	def exit (self, asyncId, lineno):
		if len(self.stack) == 0:
			return
		pop=self.stack.pop()
	
		if pop == asyncId and asyncId in self.cbs:
			self.cbs[asyncId].addEnd(lineno)
		pass

	def addCb (self, cb):
		#1.save the param cb in self.cbs
		self.cbs[cb.asyncId]=cb
		
		#2.save the cb.asyncId into its prior cb	
		if cb.prior != None and cb.prior in self.cbs:
			self.cbs[cb.prior].addPostCb(cb)
			#note: it is possible for the global script to register callbacks after the script exit
			#we do not consider the registration instruction any more
			'''
			if not hasattr(self.cbs[cb.prior], 'end'):
				self.cbs[cb.prior].addInstruction(cb.register)
			'''
		#3.save cb in initialized order to associate file operation with its cb
		self.cbForFile.append(cb.asyncId)
		#4.save the cb asyncId into the cb_cache to identify the test case
		self.add_in_cb_cache(cb.asyncId)
		pass
	
	def getNewestCb (self):
		# return the asyncId of last initialized callback
		res = None
		for i in range(len(self.cbForFile)-1, -1, -1):
			if self.cbs[self.cbForFile[i]].priority == 3:
				return self.cbForFile[i]
		pass

	def addDARecord (self, rcd):
		self.records[rcd.lineno]=rcd
		if isinstance(rcd, DataAccessRecord):
			self.addInVars(rcd)
		pass

	def addFileRecord (self, rcd):
		#print 'ADD A FILE RECORD'
		self.records[rcd.lineno] = rcd
		fileId = rcd.getId()
		if not self.files.has_key(fileId):
			self.files[fileId] = list()
		self.files[fileId].append(rcd.lineno)
		pass	

	def addInVars (self, daRcd):
		#the new addInVars is to add the lineno of the daRcd into self.vars instead of cb

		varId=daRcd.getId()
		if not self.vars.has_key(varId):
			self.vars[varId]=dict()
			self.vars[varId]['W']=list()
			self.vars[varId]['R']=list()
		if 'R'==daRcd.accessType and daRcd.lineno not in self.vars[varId]['R']:
			self.vars[varId]['R'].append(daRcd.lineno)
		elif 'W'==daRcd.accessType and daRcd.lineno not in self.vars[varId]['W']:
			self.vars[varId]['W'].append(daRcd.lineno)
		pass

class FunStack:
	
	def __init__(self):
		"""
			@stack <list>: store the iid of each function instruction
			@counts <dict>: store the times of each iid (function) is entered, i.e., counts[iid]
			@vars <dict>: store the variables of each iid (function), i.e., vars[iid-times][name]=true/false
		"""
		#set the first element in the self.stack to 0: assume the global script as a function with iid 0
		#self.stack=['0']
		self.stack=[]
		#set the time that the global script is entered is 1
		#self.counts={'0':1}
		self.counts={}
		self.vars={}
		pass
	
	def top(self):
		return self.stack[len(self.stack)-1]
		pass

	def enter(self, iid):
		self.stack.append(iid)
		if not self.counts.has_key(iid):
			self.counts[iid]=0
		self.counts[iid]+=1
		if not self.vars.has_key(self.getId()):
			self.vars[self.getId()]={}
		#print('After enter func %s, vars: %s' %(iid, self.vars))
		pass

	def exit(self):
		#if len(self.stack) > 0:
		self.stack.pop()	
		pass

	def getId(self):
		if len(self.stack) == 0:
			return
		topFunc=self.top()
		return topFunc+'-'+str(self.counts[topFunc])
		pass

	def declare(self, name):
		#print("DECLARE %s" %(name))
		#print(type(name))
		if not self.vars.has_key(self.getId()):
			return
		if type(name)==str:
			self.vars[self.getId()][name]=True
		#print('After declare %s, vars: %s' %(name, self.vars))
		pass

	def isDeclaredLocal(self, name):
		if not self.vars.has_key(self.getId()):
			return False
		#if name == 'client':
			#print("Get isDeclaredLocal of var %s: %s" %(name, self.vars[self.getId()].has_key(name)))
		return self.vars[self.getId()].has_key(name)
		pass
	
class DataAccessRecord:

	count=0	

	def __init__ (self, lineno, entryType, accessType, ref, name, eid, iid):
		self.lineno=lineno
		self.entryType=entryType
		self.accessType=accessType
		self.ref=ref
		self.name=name
		self.eid=eid
		self.iid=iid	
		pass

	def getId (self):
		#input: a data accessing record
		#return: the string 'scope@name'
		return self.ref+'@'+self.name	

	def toString (self):
		return print_obj(self, ['lineno', 'location', 'cbLoc', 'iid', 'accessType', 'logEntryType', 'ref', 'name', 'eid', 'etp'])
		pass

class FileAccessRecord (object):

	def __init__ (self, lineno, entryType, accessType, resource, ref, name, eid, location, isAsync):
		self.lineno = lineno
		self.entryType = entryType
		self.accessType = accessType
		self.resource = resource
		self.ref = ref
		self.name = name
		self.eid = eid
		self.location = location
		self.isAsync = isAsync
		pass

	def getId (self):
		return self.resource
		pass

	def toString (self):
		return print_obj(self, ['lineno', 'entryType', 'accessType', 'resource', 'ref', 'name', 'eid', 'location', 'isAsync'])
		pass
'''
class StartandEndRecord:

	def __init__ (self, asyncId, insType, lineno):
		self.asyncId=asyncId
		self.type=insType
		self.lineno=lineno
		pass
'''

_identifier = {
	"read[s|S]tream": {
		"read": "FS_READ",
		"close": "FS_CLOSE",
		"end": "FS_CLOSE"
	},
	"write[w|W]tream":{
		"write": "FS_WRITE",
		"close": "FS_CLOSE",
		"end": "FS_CLOSE"
	},
	"fs":{
		"write|append|truncate": "FS_WRITE",
		"unlink|rmdir": "FS_DELETE",
		"read": "FS_READ",
		"access|exists|stat": "FS_STAT",
		#"copy"
		#"link"
		#"rename"
		"open": "FS_OPEN",
		"close": "FS_CLOSE",
		"mkdir": "FS_CREATE",
		"end": "FS_CLOSE"
	}
}

class Helper:
	
	def	__init__ (self):
		self.stack = list()
		self.location_map = dict()
		self.latestTargetFile = None
		pass

	def createStream (self, source):
		#print("Find a create Stream\n")
		self.latestTargetFile = source
		pass

	def saveIntoMap (self, streamHandler):
		self.location_map[streamHandler] = self.latestTargetFile
		pass
	
	def getResource (self):
		return self.latestTargetFile
		pass
	
	def isEnter (self, name):
		if len(self.stack) == 0:
			for key in _identifier.keys():
				if re.search(key, name):
					return True
		elif len(self.stack) == 1:
			first = self.stack[0]
			#print(self.stack)
			#print(first)
			#print(_identifier)
			for key in _identifier:
				if re.search(key, first):
					stop = key
					break
			for key in _identifier[stop]:
				if re.search(key, name):
					return True
			#if name in _identifier[stop]:
				#return True
		return False
		pass

	def enter (self, fName):
		self.stack.append(fName)
		#print("Enter %s" %(self.stack))
		#if len(self.stack) == 2:
			#self.identify_fs_operation()
		pass
	
	def isCheck (self):
		return len(self.stack) == 2
		pass

	def identify_fs_operation (self):
		find = None
		stop_1 = None
		stop_2 = None
		for key in _identifier:
			if re.search(key, self.stack[0]):
				stop_1 = key
				break
		for key in _identifier[stop_1]:
			if re.search(key, self.stack[1]):
				find = True
				stop_2 = key
				break
		if find:
			accessType = _identifier[stop_1][stop_2]
		else:
			accessType = 'unknown'
		self.stack = list()
		return accessType	
		pass

def processLine (line):

	#@param line <str>: each line in the trace file
	
	global lineno
	global sourceMap
	global currentSourceFile
	global funCtx
	global cbCtx
	#global records
	global helper
	global waitingResource
	global underSetStream
	global _fs
	global _fileName
	global fAccessType
	global lastManualFile
	global lastfunName
	global lastfsresolve
	#global lastRegister

	lineno+=1
	record=None
	register = None
	resolve = None
	
	if line:
		
		#print lineno
		#print '%d\r'%(lineno)
		#print(lineno, end="\r"i)
		
		if lineno == 4136:
			print(lineno)
			print('======line is: %s' %(line))
	
		item=line.split(",")
		itemEntryType=item[0]
		if type(itemEntryType)!="int" and itemEntryType != 'undefined':
			itemEntryType=int(itemEntryType)
		if not LogEntryType.has_key(itemEntryType):
			return
		itemEntryTypeName=LogEntryType[itemEntryType]
		test_case_key = 'GoodBye'
		if VarAccessType.has_key(itemEntryTypeName):
			record=DataAccessRecord(lineno, itemEntryTypeName, VarAccessType[itemEntryTypeName], item[2], item[3], cbCtx.top(), item[1])
			#identify test case
			if itemEntryTypeName == 'WRITE' and item[3] == test_case_key:
				cbCtx.identify_test_case()
			
			#check if there is a file operation

			
			if VarAccessType[itemEntryTypeName] == 'R': 
				'''	
				if waitingResource:
					helper.createStream(item[3])
					#print("Get waitingResource: lineno %s" %(lineno))
					waitingResource = False
					underSetStream = True
				elif item[3] == 'createReadStream' or item[3] == 'createWriteStream':
					#print("Set waitingResource: lineno %s" %(lineno))
					waitingResource = True
				elif helper.isEnter(item[3]):
					helper.enter(item[3])
					if helper.isCheck():
						accessType = helper.identify_fs_operation()
						resource = helper.getResource()
						#print("Retrive resource: %s" %(resource))
						conj = "#"
						location = conj.join(sourceMap[item[1]])
						#it seems no matter if we lose this DataAccessRecord
						record = FileAccessRecord(lineno, accessType, FileAccessType[accessType], resource, item[2], item[3], cbCtx.top(), location, True)
						if lineno == 4136:
							print("1. Find resource %s" %(print_obj(record, ['lineno', 'entryType', 'resource'])))
						#print("1. Find resource %s" %(resource))
						record.cb = None
				'''			
				if item[3] == 'fs' or item[3] == '_fs2':
					_fs = True
				elif _fs:
					for key in _identifier["fs"]:
						if re.search(key, item[3], re.I):
							fAccessType = _identifier["fs"][key]
							break
					if fAccessType:
						_fileName = True
					_fs = False
					lastfunName = item[3]
					#print("name: %s" %(item[3]))
				elif _fileName:
					fileName = item[3]
					conj = "#"
					location = conj.join(sourceMap[item[1]])
					isAsync = re.search("sync", lastfunName, re.I)
					if isAsync != None:
						isAsync = False
					else:
						isAsync = True
					#if fAccessType == 'FS_READ':
						#print("Find type : %s, resource: %s %s %s" %(lastfunName, fileName, isAsync, lineno))
					#print("Resource %s" %(fileName))
					record = FileAccessRecord(lineno, fAccessType, FileAccessType[fAccessType], fileName, item[2], lastfunName, cbCtx.top(), location, isAsync)
					#if lineno == 4136:
						#print("2. Find resource %s" %(print_obj(record, ['lineno', 'entryType', 'resource'])))
					#if lineno == 14570:
						#print(print_obj(record, ['name', 'resource', 'isAsync']))
					if isAsync == False:
						record.cb = None
					else:
						lastManualFile = lineno
					_fileName = None
			else:
				if underSetStream and re.search("[read|write]stream", item[3], re.I):
					#associate source with its stream
					helper.saveIntoMap(item[3])
					underSetStream = False
			
			
		elif FileAccessType.has_key(itemEntryTypeName):	
			if item[6] == '1':
				isAsync = True
			else:
				isAsync = False
			record = FileAccessRecord(lineno, itemEntryTypeName, FileAccessType[itemEntryTypeName], item[1], item[2], item[3], cbCtx.top(), item[5], isAsync)
			#if lineno == 4136:
				#print("3. Find resource %s" %(print_obj(record, ['lineno', 'entryType', 'resource'])))	
			#print("3. Find resource %s" %(item[1]))
			if record.isAsync == True:
				#associate asynchronous file operation with its callback
				record.cb = cbCtx.getNewestCb()
				#if lineno == 1368:
					#print(print_obj(record, ['lineno', 'cb', 'isAsync']))
				#associate the generated Reg_or_Resolve_Op instance with the file operation
				record.resolve = str(cbCtx.cbs[record.cb].register) + 'rr' 
				#record.resolve = lastfsresolve
				#associatedCb = cbCtx.cbs[record.cb]
				'''
				register = Reg_or_Resolve_Op(associatedCb.prior, associatedCb.asyncId, associatedCb.resourceType, str(lineno) + 'r')
				resolve = Reg_or_Resolve_Op(associatedCb.prior, associatedCb.asyncId, associatedCb.resourceType, str(lineno) + 'rr')
				record.register = register.lineno
				record.resolve = resolve.lineno
				'''
				#if lineno == 1368:
					#print(print_obj(record, ['lineno', 'cb', 'isAsync', 'register', 'resolve', 'eid']))
		elif itemEntryType==LogEntryType["ASYNC_INIT"]:	
		
			cb=Callback(item[1], item[3], item[2], 'register', lineno)
			cbCtx.addCb(cb)
			#if cb.asyncId == '11758':
				#print(print_obj(cb, ['asyncId', 'prior', 'lineno']))
			
			#if cb.asyncId == "169":
				#print("processLine-debug: %s" %(lastManualFile))
			#deal with manually identified file access
			if lastManualFile:
				cbCtx.records[lastManualFile].cb = item[1]
				cbCtx.records[lastManualFile].resolve = str(lineno) + 'rr'
				lastManualFile = None

			#generate Reg_or_Resolve_Op instance
			register = Reg_or_Resolve_Op(item[3], item[1], item[2], str(lineno) + 'r')
			#if item[2] == 'TickObject' or item[2] == 'Immediate' or item[2] == 'Timeout':
			resolve = Reg_or_Resolve_Op(item[3], item[1], item[2], str(lineno) + 'rr')
			if cb.resourceType in ['FSEVENTWRAP', 'FSREQCALLBACK']:
				lastfsresolve = resolve.lineno
			#print(cbCtx.cbs)
			#print(cbCtx.stack)
			#there is a cb, whose asyncId is 0
			#if lineno == 1955:
				#print("debug for 39: %s" %(cbCtx.cbs.keys()))
			if item[3] in cbCtx.cbs and item[3] != '0':
				cbCtx.cbs[item[3]].addRecord(register)
				cbCtx.cbs[item[3]].addRecord(resolve)
				cbCtx.save_register_resolve(register)
				cbCtx.save_register_resolve(resolve)
				'''	
				if lineno == 8546:
					print("debug records for 39: %s %s" %(cbCtx.cbs[item[3]].asyncId, cbCtx.cbs[item[3]].records))
					print(item[3])
				'''
				register = None
				resolve = None
			#else:
				#lastRegister = register
		elif itemEntryType==LogEntryType["ASYNC_BEFORE"]:	
			#if lineno == 5783:
				#print("OK")
			cbCtx.enter(item[1], lineno)	
		elif itemEntryType==LogEntryType["ASYNC_AFTER"]:
			cbCtx.exit(item[1], lineno)	
		elif itemEntryType==LogEntryType["ASYNC_PROMISERESOLVE"]:	
			if item[1] not in cbCtx.cbs:
				cb=Callback(item[1], item[2], 'RESOLVE', 'resolve', lineno)
				cbCtx.addCb(cb)
				register = Reg_or_Resolve_Op(item[2], item[1], 'RESOLVE', str(lineno) + 'r')
				resolve = Reg_or_Resolve_Op(item[2], item[1], 'RESOLVE', str(lineno) + 'rr')
				if item[2] in cbCtx.cbs:	
					cbCtx.cbs[item[2]].addRecord(register)
					cbCtx.cbs[item[2]].addRecord(resolve)
					cbCtx.save_register_resolve(register)
					cbCtx.save_register_resolve(resolve)
			'''
			if lineno == 6292:
				print('debug-PROMISE: %s' %(cbCtx.cbs[item[2]].records))		
			if lineno == 6298:
				print('debug-PROMISE: %s' %(cbCtx.cbs[item[2]].records))
			#if cb.asyncId == '11758':
				#print(print_obj(cb, ['asyncId', 'prior', 'lineno']))
			'''
		elif itemEntryType==LogEntryType["SCRIPT_ENTER"]:
			
			currentSourceFile=item[3]
			#register: assume asyncId='0', prior=None, hbType='register', resourceType='GLOBALCB' but no constraint
			#note: asyncId is '1' rather than '0' in order to be the same with the prior cb of callbacks the glocal script registers
			#record=HappensBeforeRecord (lineno, '0', None, 'register', 'GLOBALCB')
			asyncId = cbCtx.get_script_count()
			cb=Callback(asyncId, None, 'GLOBALCB', 'register', lineno)
			cbCtx.addCb(cb)	
			#before: assume eid='0'
			#cbCtx.enter('0')
			#to make each instruction has a unique lineno
			lineno=lineno+1
			cbCtx.enter(cb.asyncId, lineno)
			#add register and resolve op for the global script "callback" and save them into records
			#register = Reg_or_Resolve_Op(None, '1', 'GLOBALCB', str(lineno) + 'r')
			#resolve = Reg_or_Resolve_Op(None, '1', 'GLOBALCB', str(lineno) + 'rr')
			#cbCtx.cbs['1'].addRecord(register)
			#cbCtx.cbs['1'].addRecord(resolve)
			#cbCtx.save_register_resolve(register)
			#cbCtx.save_register_resolve(resolve)
			#function_enter	
			funCtx.enter(item[1])
			
		elif itemEntryType==LogEntryType["SCRIPT_EXIT"]:
			#cb after
			cbCtx.exit('1', lineno)
			#TODO: add function exit
		elif itemEntryType==LogEntryType["SOURCE_MAPPING"]:
			lst=[currentSourceFile]
			sourceMap[item[1]]=lst+item[2:6]
		elif itemEntryType==LogEntryType["FUNCTION_ENTER"]:
			funCtx.enter(item[1])
		elif itemEntryType==LogEntryType["FUNCTION_EXIT"]:
			funCtx.exit()
		elif itemEntryType==LogEntryType["DECLARE"]:	
			funCtx.declare(item[3])

	#add following information for each data accessing record: location, isDeclaredLocal, etp and cbLoc
	if isinstance(record, DataAccessRecord) or isinstance(record, FileAccessRecord):
		#location
		conj='#'	
		if not hasattr(record, 'location'):
			#sth wierd! some iid has no location in sourceMap
			if record.iid in sourceMap:
				record.location=conj.join(sourceMap[record.iid])
			else:
				record.location = 'unknown'
		#isDeclaredLocal
		record.isDeclaredLocal=funCtx.isDeclaredLocal(record.name)
		#etp/TODO	
		if record.eid == '0':
			env = None
		#wierd: some cb starts even if no registration or triggering
		elif record.eid in cbCtx.cbs:
			#print(cbCtx.cbs.keys())
			env=cbCtx.cbs[record.eid]	
		else:
			env = None
		record.etp=env.resourceType if env else None
		#cbLoc
		cbLoc = env.getCbLoc() if env != None else None
		record.cbLoc=cbLoc if cbLoc else record.location	
	
		if isinstance(record, DataAccessRecord):
			#1. save record in records
			cbCtx.addDARecord(record)
			#2. associate record with its event
			if cbCtx.top() in cbCtx.cbs:
				cbCtx.cbs[cbCtx.top()].addRecord(record)
			#isDeclaredLocal for false positive
		else:
			#cbCtx.addFileRecord(record)
			#print(cbCtx.top() in cbCtx.cbs)
			if cbCtx.top() in cbCtx.cbs or record.eid != '0':
				cbCtx.addFileRecord(record)
				'''
				if hasattr(record, 'register'):	
					cbCtx.cbs[cbCtx.top()].addRecord(register)
					cbCtx.save_register_resolve(register)
				'''
				cbCtx.cbs[cbCtx.top()].addRecord(record)
				'''
				if hasattr(record, 'resolve'):
					cbCtx.cbs[cbCtx.top()].addRecord(resolve)
					cbCtx.save_register_resolve(resolve)
				'''
	pass		

def searchFile (directory, filePrefix):
	#search all the files that have the @filePrefix in the dir @directory
	#@return <list>: the list of file name <str>
	
	fileList = list()
	for root, dirs, files in os.walk(directory):
		for f in files:
			if f.startswith(filePrefix):
				fileList.append(os.path.join(root, f))
	return fileList
	pass

def processTraceFile (traceFile):

	'''
	@param traceFile <str>: the trace file to be parsed
	@return result <dict>: stores the collection of records (start/end, data access, register/resolve) <dict> indexed by lineno, cbs <dict> indexed by asyncId, cbsByPriority <dict> indexed by priorAsyncId
	'''
	#TODO: add python stdout 
	#print "======Begin to parse the trace file %s" %(traceFile)
		
	with open(traceFile) as f:
		line=f.readline()
		while line:
			processLine(line.strip())
			line=f.readline()
	'''
	rootPath = os.path.dirname(os.path.realpath(traceFile))
	fileName = 'ascii-trace'
	traceFileList = searchFile(rootPath, fileName)
	traceFileList.sort()

	for fileName in traceFileList:
		print("~~~~~~ENTER TRACEFILE %s ~~~~~~" %(fileName))
		
		with open(fileName) as f:
			line = f.readline()
			while line:
				processLine(line.strip())
				line = f.readline()
	'''
	
	result=dict()	
	result['cbs']=cbCtx.cbs
	#print("debug-processtracefile: %s" %(print_obj(cbCtx.cbs['39'], ['records'])))
	result['records']=cbCtx.records
	result['vars']=cbCtx.vars
	result['files'] = cbCtx.files
	
	#if we only run a test case but not a test suit
	if len(cbCtx.testsuit) == 0:
		cbCtx.testsuit[0] = cbCtx.cb_cache
	result['testsuit'] = cbCtx.testsuit
	'''
	print('debug-tracefile: ')
	for testcase in cbCtx.testsuit.values():
		print(testcase)
		print('\n')
	'''
	print("*******COMPLETE PARSE TRACE*****")
	return result
	pass

def main():
	traceFile=sys.argv[1]
	if sys.argv[2] == 't':
		isRace=True 
	else:
		isRace=False
	if sys.argv[3] == 't':
		isChain = True
	else:
		isChain = False
	#step 1: parse record into object
	parsedResult=processTraceFile(traceFile)
	
	pass

lineno=-1
sourceMap={}
currentSourceFile=None
funCtx=FunStack()
cbCtx=CbStack()
#records=dict()
helper = Helper()
waitingResource = None
underSetStream = None
_fs = None
_fileName = None
fAccessType = None
lastManualFile = None
lastfunName = None
lastfsresolve = None
#in order to associate  manually generated register and resolve operation with their async file operation
#lastRegister = None
