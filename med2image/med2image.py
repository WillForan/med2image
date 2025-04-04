#!/usr/bin/env python3

# System imports
import  os
from    os                  import  listdir
from    os                  import  walk
from    os.path             import  isfile, join
from    pathlib             import  Path

import  sys
import  glob
import  numpy as np
import  re
import  time
#import  pudb
from    scipy               import  ndimage
# System dependency imports
import  nibabel              as      nib
import  pydicom              as      dicom
import  pylab
import  matplotlib.cm        as      cm

import  pfmisc
from    pfmisc._colors      import  Colors
from    pfmisc.message      import  Message


#: dicom filenames are like *.dcm, *IMA, MR.*. This should be an option?
DICOMPATTS = [r'(^|/)MR\.', r'\.dcm$', r'\.IMA$']
DICOMGLOBS = ['MR*', '*.dcm', '*.IMA']


def report(     callingClass,
                astr_key,
                ab_exitToOs=1,
                astr_header=""
                ):
    '''
    Error handling.

    Based on the <astr_key>, error information is extracted from
    _dictErr and sent to log object.

    If <ab_exitToOs> is False, error is considered non-fatal and
    processing can continue, otherwise processing terminates.
    '''
    log         = callingClass.log()
    b_syslog    = log.syslog()
    log.syslog(False)
    if ab_exitToOs: log( Colors.RED +    "\n:: FATAL ERROR :: " + Colors.NO_COLOUR )
    else:           log( Colors.YELLOW + "\n::   WARNING   :: " + Colors.NO_COLOUR )
    if len(astr_header): log( Colors.BROWN + astr_header + Colors.NO_COLOUR )
    log( "\n" )
    log( "\tSorry, some error seems to have occurred in:\n\t<" )
    log( Colors.LIGHT_GREEN + ("%s" % callingClass.name()) + Colors.NO_COLOUR + "::")
    log( Colors.LIGHT_CYAN + ("%s" % inspect.stack()[2][4][0].strip()) + Colors.NO_COLOUR)
    log( "> called by <")
    try:
        caller = inspect.stack()[3][4][0].strip()
    except:
        caller = '__main__'
    log( Colors.LIGHT_GREEN + ("%s" % callingClass.name()) + Colors.NO_COLOUR + "::")
    log( Colors.LIGHT_CYAN + ("%s" % caller) + Colors.NO_COLOUR)
    log( ">\n")

    log( "\tWhile %s" % callingClass._dictErr[astr_key]['action'] )
    log( "\t%s" % callingClass._dictErr[astr_key]['error'] )
    log( "\n" )
    if ab_exitToOs:
        log( "Returning to system with error code %d\n" % \
                        callingClass._dictErr[astr_key]['exitCode'] )
        sys.exit( callingClass._dictErr[astr_key]['exitCode'] )
    log.syslog(b_syslog)
    return callingClass._dictErr[astr_key]['exitCode']


def fatal( callingClass, astr_key, astr_extraMsg="" ):
    '''
    Convenience dispatcher to the error_exit() method.
    Will raise "fatal" error, i.e. terminate script.
    '''
    b_exitToOS  = True
    report( callingClass, astr_key, b_exitToOS, astr_extraMsg )


def warn( callingClass, astr_key, astr_extraMsg="" ):
    '''
    Convenience dispatcher to the error_exit() method.
    Will raise "warning" error, i.e. script processing continues.
    '''
    b_exitToOS = False
    report( callingClass, astr_key, b_exitToOS, astr_extraMsg )

class med2image(object):
    """
        med2image accepts as input certain medical image formatted data
        and converts each (or specified) slice of this data to a graphical
        display format such as png or jpg.

    """

    _dictErr = {
        'inputFileFail'   : {
            'action'        :   'trying to read input file, ',
            'error'         :   'could not access/read file -- does it exist? Do you have permission?',
            'exitCode'      :   10},
        'emailFail'   : {
            'action'        :   'attempting to send notification email, ',
            'error'         :   'sending failed. Perhaps host is not email configured?',
            'exitCode'      :   20},
        'dcmInsertionFail': {
            'action'        :   'attempting insert DICOM into volume structure, ',
            'error'         :   'a dimension mismatch occurred. This DICOM file is of different image size to the rest.',
            'exitCode'      :   30},
        'ProtocolNameTag': {
            'action'        :   'attempting to parse DICOM header, ',
            'error'         :   'the DICOM file does not seem to contain a ProtocolName tag.',
            'exitCode'      :   40},
        'PatientNameTag':   {
            'action':           'attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a PatientName tag.',
            'exitCode':         41},
        'PatientAgeTag': {
            'action': '         attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a PatientAge tag.',
            'exitCode':         42},
        'PatientNameSex': {
            'action':           'attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a PatientSex tag.',
            'exitCode':         43},
        'PatientIDTag': {
            'action':           'attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a PatientID tag.',
            'exitCode':         44},
        'SeriesDescriptionTag': {
            'action':           'attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a SeriesDescription tag.',
            'exitCode':         45},
        'PatientSexTag': {
            'action':           'attempting to parse DICOM header, ',
            'error':            'the DICOM file does not seem to contain a PatientSex tag.',
            'exitCode':         46}
    }

    @staticmethod
    def mkdir(newdir, mode=0x775):
        """
        works the way a good mkdir should :)
            - already exists, silently complete
            - regular file in the way, raise an exception
            - parent directory(ies) does not exist, make them as well
        """
        if os.path.isdir(newdir):
            pass
        elif os.path.isfile(newdir):
            raise OSError("a file with the same name as the desired " \
                        "dir, '%s', already exists." % newdir)
        else:
            Path(newdir).mkdir(parents = True, exist_ok = True)
        #     head, tail = os.path.split(newdir)
        #     if head and not os.path.isdir(head):
        #         os.mkdirs(head, exist_ok=True)
        #     if tail:
        #         os.mkdirs(newdir, exist_ok=True)

    def log(self, *args):
        '''
        get/set the internal pipeline log message object.

        Caller can further manipulate the log object with object-specific
        calls.
        '''
        if len(args):
            self._log = args[0]
        else:
            return self._log

    def name(self, *args):
        '''
        get/set the descriptive name text of this object.
        '''
        if len(args):
            self.__name = args[0]
        else:
            return self.__name

    def description(self, *args):
        '''
        Get / set internal object description.
        '''
        if len(args):
            self.str_desc = args[0]
        else:
            return self.str_desc

    @staticmethod
    def urlify(astr, astr_join = '_'):
        # Remove all non-word characters (everything except numbers and letters)
        # pudb.set_trace()
        astr = re.sub(r"[^\w\s]", '', astr)

        # Replace all runs of whitespace with an underscore
        astr = re.sub(r"\s+", astr_join, astr)

        return astr

    def __init__(self, **kwargs):

        #
        # Object desc block
        #
        self.str_desc                   = ''
        # self._log                        = msg.Message()
        # self._log._b_syslog              = True
        self.__name__                    = "med2image"

        # Directory and filenames
        self.str_workingDir             = ''
        self.str_inputFile              = ''
        self.lstr_inputFile             = []
        self.str_inputFileSubStr        = ''
        self.str_outputFileStem         = ''
        self.str_outputFileType         = ''
        self.str_outputDir              = ''
        self.str_inputDir               = ''

        self._b_convertAllSlices        = False
        self.str_sliceToConvert         = ''
        self.str_frameToConvert         = ''
        self._sliceToConvert            = -1
        self._frameToConvert            = -1

        self.str_stdout                 = ""
        self.str_stderr                 = ""
        self._exitCode                  = 0

        # The actual data volume and slice
        # are numpy ndarrays
        self._b_4D                      = False
        self._b_3D                      = False
        self._b_DICOM                   = False
        self.convertOnlySingleDICOM     = False
        self.preserveDICOMinputName     = False
        self._Vnp_4DVol                 = None
        self._Vnp_3DVol                 = None
        self._Mnp_2Dslice               = None
        self._dcm                       = None
        self._dcmList                   = []

        self.verbosity                  = 1

        # Flags
        self._b_showSlices              = False
        self._b_convertMiddleSlice      = False
        self._b_convertMiddleFrame      = False
        self._b_reslice                 = False
        self.func                       = None  # transformation function
        self.rot                        = '110'
        self.rotAngle                   = 90

        for key, value in kwargs.items():
            if key == "inputFile":              self.str_inputFile          = value
            if key == "inputFileSubStr":        self.str_inputFileSubStr    = value
            if key == "inputDir":               self.str_inputDir           = value
            if key == "outputDir":              self.str_outputDir          = value
            if key == "outputFileStem":         self.str_outputFileStem     = value
            if key == "outputFileType":         self.str_outputFileType     = value
            if key == "sliceToConvert":         self.str_sliceToConvert     = value
            if key == "frameToConvert":         self.str_frameToConvert     = value
            if key == "convertOnlySingleDICOM": self.convertOnlySingleDICOM = value
            if key == "preserveDICOMinputName": self.preserveDICOMinputName = value
            if key == "showSlices":             self._b_showSlices          = value
            if key == 'reslice':                self._b_reslice             = value
            if key == "func":                   self.func                   = value
            if key == "verbosity":              self.verbosity              = int(value)
            if key == "rot":                    self.rot                    = value
            if key == "rotAngle":               self.rotAngle               = int(value)

        # A logger
        self.dp                         = pfmisc.debug(
                                            verbosity   = self.verbosity,
                                            within      = self.__name__
                                            )
        self.LOG                        = self.dp.qprint

        if self.str_frameToConvert.lower() == 'm':
            self._b_convertMiddleFrame = True
        elif len(self.str_frameToConvert):
            self._frameToConvert = int(self.str_frameToConvert)

        if self.str_sliceToConvert.lower() == 'm':
            self._b_convertMiddleSlice = True
        elif len(self.str_sliceToConvert):
            self._sliceToConvert = int(self.str_sliceToConvert)

        if len(self.str_inputDir):
            self.str_inputFile  = '%s/%s' % (self.str_inputDir, self.str_inputFile)
        if not len(self.str_inputDir):
            self.str_inputDir = os.path.dirname(self.str_inputFile)
        if not len(self.str_inputDir): self.str_inputDir = '.'
        str_fileName, str_fileExtension  = os.path.splitext(self.str_outputFileStem)
        if len(self.str_outputFileType):
            str_fileExtension            = '.%s' % self.str_outputFileType

        if len(str_fileExtension) and not len(self.str_outputFileType):
            self.str_outputFileType     = str_fileExtension

        if not len(self.str_outputFileType) and not len(str_fileExtension):
            self.str_outputFileType     = 'png'

    def tic(self):
        """
            Port of the MatLAB function of same name
        """
        global Gtic_start
        Gtic_start = time.time()

    def toc(self, *args, **kwargs):
        """
            Port of the MatLAB function of same name

            Behaviour is controllable to some extent by the keyword
            args:


        """
        global Gtic_start
        f_elapsedTime = time.time() - Gtic_start
        for key, value in kwargs.items():
            if key == 'sysprint':   return value % f_elapsedTime
            if key == 'default':    return "Elapsed time = %f seconds." % f_elapsedTime
        return f_elapsedTime

    def run(self):
        '''
        The main 'engine' of the class.
        '''

    def echo(self, *args):
        self._b_echoCmd         = True
        if len(args):
            self._b_echoCmd     = args[0]

    def echoStdOut(self, *args):
        self._b_echoStdOut      = True
        if len(args):
            self._b_echoStdOut  = args[0]

    def stdout(self):
        return self.str_stdout

    def stderr(self):
        return self.str_stderr

    def exitCode(self):
        return self._exitCode

    def echoStdErr(self, *args):
        self._b_echoStdErr      = True
        if len(args):
            self._b_echoStdErr  = args[0]

    def dontRun(self, *args):
        self._b_runCmd          = False
        if len(args):
            self._b_runCmd      = args[0]

    def workingDir(self, *args):
        if len(args):
            self.str_workingDir = args[0]
        else:
            return self.str_workingDir

    def get_output_file_name(self, **kwargs):
        index   = 0
        frame   = 0
        str_subDir  = ""
        for key,val in kwargs.items():
            if key == 'index':  index       = val
            if key == 'frame':  frame       = val
            if key == 'subDir': str_subDir  = val

        if self._b_4D:
            str_outputFile = '%s/%s/%s-frame%03d-slice%03d.%s' % (
                                                    self.str_outputDir,
                                                    str_subDir,
                                                    self.str_outputFileStem,
                                                    frame, index,
                                                    self.str_outputFileType)
        else:
            if self.preserveDICOMinputName and (str_subDir == 'z' or str_subDir == ''):
                str_filePart    = os.path.splitext(self.lstr_inputFile[index])[0]
            else:
                str_filePart    = '%s-slice%03d' % (self.str_outputFileStem, index)
            str_outputFile      = '%s/%s/%s.%s' % (
                                        self.str_outputDir,
                                        str_subDir,
                                        str_filePart,
                                        self.str_outputFileType)
        return str_outputFile

    def dim_save(self, **kwargs):
        dims            = self._Vnp_3DVol.shape
        str_dim         = 'z'
        b_makeSubDir    = False
        b_rot90         = False
        indexStart      = -1
        indexStop       = -1
        frame           = 0
        for key, val in kwargs.items():
            if key == 'dimension':  str_dim         = val
            if key == 'makeSubDir': b_makeSubDir    = val
            if key == 'indexStart': indexStart      = val
            if key == 'indexStop':  indexStop       = val
            if key == 'rot90':      b_rot90         = val
            if key == 'frame':      frame           = val

        str_subDir  = ''
        if b_makeSubDir:
            str_subDir = str_dim
            med2image.mkdir('%s/%s' % (self.str_outputDir, str_subDir))

        dim_ix = {'x':0, 'y':1, 'z':2}
        if indexStart == 0 and indexStop == -1:
            indexStop = dims[dim_ix[str_dim]]
        self.LOG('Saving along "%s" dimension with %i degree rotation...' % (str_dim, self.rotAngle*b_rot90))
        for i in range(indexStart, indexStop):
            if str_dim == 'x':
                self._Mnp_2Dslice = self._Vnp_3DVol[i, :, :]
            elif str_dim == 'y':
                self._Mnp_2Dslice = self._Vnp_3DVol[:, i, :]
            else:
                self._Mnp_2Dslice = self._Vnp_3DVol[:, :, i]
            self.process_slice(b_rot90)
            str_outputFile = self.get_output_file_name(index=i, subDir=str_subDir, frame=frame)
            if str_outputFile.endswith('dcm'):
                self._dcm = self._dcmList[i]
            self.slice_save(str_outputFile)
        self.LOG('%d images saved along "%s" dimension' % ((i+1), str_dim),
                end = '')
        if self.func:
            self.LOG(" with '%s' function applied." % self.func,
                syslog = False)
        else:
            self.LOG(".", syslog = False)

    def process_slice(self, b_rot90 = False):
        '''
        Processes a single slice.
        '''
        if b_rot90:
            self._Mnp_2Dslice = ndimage.rotate(self._Mnp_2Dslice, self.rotAngle)
        if self.func == 'invertIntensities':
            self.invert_slice_intensities()

    def slice_save(self, astr_outputFile):
        '''
        ARGS

        o astr_output
        The output filename.
        '''
        self.LOG('Input file = %s' % self.str_inputFile, level = 3)
        self.LOG('Outputfile = %s' % astr_outputFile, level = 3)
        fformat = astr_outputFile.split('.')[-1]
        if fformat == 'dcm':
            if self._dcm:
                self._dcm.pixel_array.flat = self._Mnp_2Dslice.flat
                self._dcm.PixelData = self._dcm.pixel_array.tostring()
                self._dcm.save_as(astr_outputFile)
            else:
                raise ValueError('dcm output format only available for DICOM files')
        else:
            pylab.imsave(astr_outputFile, self._Mnp_2Dslice, format=fformat, cmap = cm.Greys_r)

    def invert_slice_intensities(self):
        '''
        Inverts intensities of a single slice.
        '''
        self._Mnp_2Dslice = self._Mnp_2Dslice*(-1) + self._Mnp_2Dslice.max()


class med2image_dcm(med2image):

    def tic(self):
        return super().tic()

    def toc(self):
        return super().toc()

    '''
    Sub class that handles DICOM data.
    '''
    def __init__(self, **kwargs):
        med2image.__init__(self, **kwargs)

        dcmfiles = [dcmfile
                    for patt in DICOMGLOBS
                    for dcmfile in glob.glob(os.path.join(self.str_inputDir,patt))]
        self.l_dcmFileNames = sorted(dcmfiles)
        self.slices         = len(self.l_dcmFileNames)
        if self._sliceToConvert != -1 or self.convertOnlySingleDICOM:
            if self._b_convertMiddleSlice:
                self._sliceToConvert    = int(self.slices/2)
                self._dcm               = dicom.dcmread(self.l_dcmFileNames[self._sliceToConvert],force=True)
                self.str_inputFile      = self.l_dcmFileNames[self._sliceToConvert]
            if not self._b_convertMiddleSlice and self._sliceToConvert != -1:
                self._dcm               = dicom.dcmread(self.l_dcmFileNames[self._sliceToConvert],force=True)
                self.str_inputFile      = self.l_dcmFileNames[self._sliceToConvert]
            else:
                self._dcm               = dicom.dcmread(self.str_inputFile,force=True)
            if self.convertOnlySingleDICOM:
                self._sliceToConvert    = 1
                self._dcm               = dicom.dcmread(self.str_inputFile,force=True)
            self.lstr_inputFile.append(os.path.basename(self.str_inputFile))
        else:
            self._b_3D              = True
            self._dcm               = dicom.dcmread(self.str_inputFile,force=True)
            image                   = self._dcm.pixel_array
            shape2D                 = image.shape
            #print(shape2D)
            self._Vnp_3DVol         = np.empty( (shape2D[0], shape2D[1], self.slices) )
            i                       = 0
            for img in self.l_dcmFileNames:
                self._dcm           = dicom.dcmread(img,force=True)
                self.lstr_inputFile.append(os.path.basename(img))
                image               = self._dcm.pixel_array
                self._dcmList.append(self._dcm)
                #print('%s: %s' % (img, image.shape))
                try:
                    self._Vnp_3DVol[:,:,i] = image
                except Exception as e:
                    self.warn(
                    'dcmInsertionFail',
                    '\nFor input DICOM file %s, %s' % (img, str(e)),
                    True)
                i += 1
        if self.str_outputFileStem.startswith('%'):
            str_spec                = self.str_outputFileStem
            self.str_outputFileStem = ''
            for key in str_spec.split('%')[1:]:
                str_fileComponent   = ''
                if key == 'inputFile':
                    str_fileName, str_ext   = os.path.splitext(self.str_inputFile)
                    str_fileComponent       = str_fileName
                else:
                    # pudb.set_trace()
                    str_fileComponent       = eval('str(self._dcm.%s)' % key)
                    str_fileComponent       = med2image.urlify(str_fileComponent)
                if not len(self.str_outputFileStem):
                    self.str_outputFileStem = str_fileComponent
                else:
                    self.str_outputFileStem = self.str_outputFileStem + '-' + str_fileComponent
        image = self._dcm.pixel_array
        self._Mnp_2Dslice = image

    @staticmethod
    def sanitize(value):
        # convert to string and remove trailing spaces
        tvalue = str(value).strip()
        # only keep alpha numeric characters and replace the rest by "_"
        svalue = "".join(character if character.isalnum() else '.' for character in tvalue)
        if not svalue:
            svalue = "no value provided"
        return svalue

    def processDicomField(self, dcm, field):
        value = "no value provided"
        if field in dcm:
            value = med2image_dcm.sanitize(dcm.data_element(field).value)
        return value

    def warn(self, str_tag, str_extraMsg = '', b_exit = False):
        '''
        Print a warning using the passed <str_tag>
        '''
        str_action      = med2image._dictErr[str_tag]['action']
        str_error       = med2image._dictErr[str_tag]['error']
        exitCode        = med2image._dictErr[str_tag]['exitCode']
        self.LOG(
            'Some error seems to have occured!', comms = 'error'
        )
        self.LOG(
            'While %s' % str_action, comms = 'error'
        )
        self.LOG(
            '%s' % str_error, comms = 'error'
        )
        if len(str_extraMsg):
            self.LOG(str_extraMsg, comms = 'error')
        if b_exit:
            sys.exit(exitCode)

    def run(self):
        '''
        Runs the DICOM conversion based on internal state.
        '''
        self.LOG('DICOM conversion (ref: %s).' % self.lstr_inputFile[0])
        if self._b_convertMiddleSlice:
            self.LOG('Converting middle slice in DICOM series')
        try:
            self.LOG('\tPatientName:            %s' % self._dcm.PatientName)
        except AttributeError:
            self.LOG('\tPatientName:            %s' % 'PatientName not found in DCM header.')
            self.warn( 'PatientNameTag')
        try:
            self.LOG('\tPatientAge:             %s' % self._dcm.PatientAge)
        except AttributeError:
            self.LOG('\tPatientAge:              %s' % 'PatientAge not found in DCM header.')
            self.warn( 'PatientAgeTag')
        try:
            self.LOG('\tPatientSex:             %s' % self._dcm.PatientSex)
        except AttributeError:
            self.LOG('\tPatientSex:             %s' % 'PatientSex not found in DCM header.')
            self.warn( 'PatientSexTag')
        try:
            self.LOG('\tPatientID:              %s' % self._dcm.PatientID)
        except AttributeError:
            self.LOG('\tPatientID:              %s' % 'PatientID not found in DCM header.')
            self.warn( 'PatientIDTag')
        try:
            self.LOG('\tSeriesDescription:      %s' % self._dcm.SeriesDescription)
        except AttributeError:
            self.LOG('\tSeriesDescription:      %s' % 'SeriesDescription not found in DCM header.')
            self.warn( 'SeriesDescriptionTag')
        try:
            self.LOG('\tProtocolName:           %s' % self._dcm.ProtocolName)
        except AttributeError:
            self.LOG('\tProtocolName:           %s' % 'ProtocolName not found in DCM header.')
            self.warn( 'ProtocolNameTag')

        l_rot90 = [ bool(int(self.rot[0])), bool(int(self.rot[1])), bool(int(self.rot[2])) ]
        med2image.mkdir(self.str_outputDir)
        if not self._b_3D:
            if self.preserveDICOMinputName:
                str_outputFile  = '%s/%s.%s' % (self.str_outputDir,
                                        os.path.splitext(self.lstr_inputFile[0])[0],
                                        self.str_outputFileType)
            else:
                str_outputFile  = '%s/%s.%s' % (self.str_outputDir,
                                        self.str_outputFileStem,
                                        self.str_outputFileType)
            self.process_slice()
            self.slice_save(str_outputFile)
        if self._b_3D:
            dims            = self._Vnp_3DVol.shape
            self.LOG('Image volume logical (i, j, k) size: %s' % str(dims))
            rotCount = 0
            if self._b_reslice:
                for dim in ['x', 'y', 'z']:
                    self.dim_save(
                            dimension   = dim,
                            makeSubDir  = True,
                            rot90       = l_rot90[rotCount],
                            indexStart  = 0,
                            indexStop = -1
                        )
                    rotCount += 1
            else:
                self.dim_save(
                            dimension   = 'z',
                            makeSubDir  = False,
                            rot90       = l_rot90[2],
                            indexStart  = 0,
                            indexStop   = -1
                        )


class med2image_nii(med2image):
    '''
    Sub class that handles NIfTI data.
    '''

    def tic(self):
        return super().tic()

    def toc(self):
        return super().toc()

    def __init__(self, **kwargs):
        med2image.__init__(self, **kwargs)
        nimg = nib.load(self.str_inputFile)
        data = nimg.get_fdata()
        if data.ndim == 4:
            self._Vnp_4DVol     = data
            self._b_4D          = True
        if data.ndim == 3:
            self._Vnp_3DVol     = data
            self._b_3D          = True

    def run(self):
        '''
        Runs the NIfTI conversion based on internal state.
        '''

        self.LOG('About to perform NifTI to %s conversion...\n' %
                  self.str_outputFileType)

        frames     = 1
        frameStart = 0
        frameEnd   = 0

        sliceStart = 0
        sliceEnd   = 0

        if self._b_4D:
            self.LOG('4D volume detected.\n')
            frames = self._Vnp_4DVol.shape[3]
        if self._b_3D:
            self.LOG('3D volume detected.\n')

        if self._b_convertMiddleFrame:
            self._frameToConvert = int(frames/2)

        if self._frameToConvert == -1:
            frameEnd    = frames
        else:
            frameStart  = self._frameToConvert
            frameEnd    = self._frameToConvert + 1

        for f in range(frameStart, frameEnd):
            if self._b_4D:
                self._Vnp_3DVol = self._Vnp_4DVol[:,:,:,f]
            slices     = self._Vnp_3DVol.shape[2]
            if self._b_convertMiddleSlice:
                self._sliceToConvert = int(slices/2)

            if self._sliceToConvert == -1:
                sliceEnd    = -1
            else:
                sliceStart  = self._sliceToConvert
                sliceEnd    = self._sliceToConvert + 1

            med2image.mkdir(self.str_outputDir)
            if self._b_reslice:
                for dim in ['x', 'y', 'z']:
                    self.dim_save(dimension = dim, makeSubDir = True, indexStart = sliceStart, indexStop = sliceEnd, rot90 = True, frame = f)
            else:
                self.dim_save(dimension = 'z', makeSubDir = False, indexStart = sliceStart, indexStop = sliceEnd, rot90 = True, frame = f)

class object_factoryCreate:
    """
    A class that examines input file string for extension information and
    creates a relevant convert object (or None).

    Returns true or false denoting converter object creation.
    """

    def __init__(self, args):
        """
        Parse relevant CLI args.
        """

        def inputFile_defineFromSubStr(astr_dir):
            """
            This nested function simply determines the first
            file in the <inputDir> that has a substring in the
            filename that conforms to the <inputFileType>.

            That file becomes the <inputFile>. The <inputFileType>
            is a useful shortcut for quickly identifying and using
            a file without needing to provide its full name.
            """
            l_filesInDir    : list  = []
            l_fileHit       : list  = []
            # First, get a list of all the files in the directory
            try:
                (_, _, l_filesInDir)    = next(os.walk(astr_dir))
            except:
                return ''
            l_fileHit               = [
                s for s in l_filesInDir if args.inputFileSubStr in s
            ]
            if len(l_fileHit):
                return l_fileHit[0]
            else:
                return ''

        if len(args.inputFileSubStr):
            args.inputFile = inputFile_defineFromSubStr(args.inputDir)
            if not len(args.inputFile):
                print(  'Input dir "%s" has no files with substring "%s"' %
                        (args.inputDir, args.inputFileSubStr))
                # print('Exiting to system with code 1.')
                # sys.exit(1)

        str_outputFileStem, str_outputFileExtension = os.path.splitext(args.outputFileStem)
        if len(str_outputFileExtension):
            str_outputFileExtension = str_outputFileExtension.split('.')[1]
        try:
            str_inputFileStem, str_inputFileExtension = os.path.splitext(args.inputFile)
        except:
            sys.exit(1)

        if not len(args.outputFileType) and len(str_outputFileExtension):
            args.outputFileType = str_outputFileExtension

        if len(str_outputFileExtension):
            args.outputFileStem = str_outputFileStem

        b_niftiExt = (str_inputFileExtension == '.nii' or
                    str_inputFileExtension == '.gz')
        b_dicomExt = not b_niftiExt and (any([re.search(p, os.path.basename(args.inputFile))
                           for p in DICOMPATTS]) or
                      args.inputDir != '')

        self.C_convert  = None
        if b_niftiExt:
            self.C_convert = med2image_nii(
                inputFile               = args.inputFile,
                inputDir                = args.inputDir,
                outputDir               = args.outputDir,
                outputFileStem          = args.outputFileStem,
                outputFileType          = args.outputFileType,
                sliceToConvert          = args.sliceToConvert,
                frameToConvert          = args.frameToConvert,
                showSlices              = args.showSlices,
                func                    = args.func,
                reslice                 = args.reslice,
                verbosity               = args.verbosity
            )

            print('sliceToConvert:', args.sliceToConvert)

        elif b_dicomExt:
            self.C_convert = med2image_dcm(
                inputFile               = args.inputFile,
                inputDir                = args.inputDir,
                outputDir               = args.outputDir,
                outputFileStem          = args.outputFileStem,
                outputFileType          = args.outputFileType,
                sliceToConvert          = args.sliceToConvert,
                convertOnlySingleDICOM  = args.convertOnlySingleDICOM,
                preserveDICOMinputName  = args.preserveDICOMinputName,
                reslice                 = args.reslice,
                rot                     = args.rot,
                rotAngle                = args.rotAngle,
                func                    = args.func,
                verbosity               = args.verbosity
            )
        else:
            print(f"ERROR: dont know what to do with {args.inputFile}. not dcm or nii?")
