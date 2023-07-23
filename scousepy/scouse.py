# Licensed under an MIT open source license - see LICENSE

"""
SCOUSE - Semi-automated multi-COmponent Universal Spectral-line fitting Engine
Copyright (c) 2016-2021 Jonathan D. Henshaw
CONTACT: henshaw@mpia.de
"""

from __future__ import print_function

from astropy import units as u
from spectral_cube import SpectralCube
from astropy import wcs

from astropy import log
import numpy as np
import os
import sys
import warnings
import shutil
import time
import pyspeckit
import random
warnings.simplefilter('ignore', wcs.FITSFixedWarning)

from .stage_3 import *

from .colors import *

import matplotlib as mpl
mpl.use('qt5agg')
import matplotlib.pyplot as plt

# add Python 2 xrange compatibility, to be removed
# later when we switch to numpy loops
if sys.version_info.major >= 3:
    range = range
    proto=3
else:
    range = xrange
    proto=2

try:
    input = raw_input
except NameError:
    pass

class scouse(object):
    """
    the scouse class

    Attributes
    ==========

    Global attributes - user defined attributes
    -------------------------------------------
    These attributes are set in the config file by the user

    config : string
        Path to the configutation file of scousepy. Must be passed to each stage
    datadirectory : string
        Directory containing the datacube
    filename : string
        Name of the file to be loaded
    outputdirectory : string, optional
        Alternate output directory. Deflault is datadirectory
    fittype : string
        Compatible with pyspeckit's models for fitting different types of
        models. Defualt is Gaussian fitting.
    verbose : bool
        Verbose output to terminal
    autosave : bool
        Save the output at each stage of the process.

    Global attributes - scouse defined attributes
    ---------------------------------------------
    cube : spectral cube object
        A spectral cube object generated from the FITS input
    completed_stages : list
        a list to be updated as each stage is completed

    stage 1 - user defined attributes
    ---------------------------------
    write_moments : bool, optional
        If true, scouse will write fits files of the moment maps
    save_fig : bool, optional
        If true, scouse will output a figure of the coverage
    coverage_config_file_path : string
        File path for coverage configuration file
    nrefine : number
        Number of refinement steps - scouse will refine the coverage map
        according to spectral complexity if several wsaas are provided.
    mask_below : number
        Masking value for moment generation. This will also determine which
        pixels scouse fits
    x_range : list
        Data x range in pixels
    y_range : list
        Data y range in pixels
    vel_range : list
        Data velocity range in map units
    wsaa : list
        Width of the spectral averaging areas. The user can provide a list of
        values if they would like to refine the coverage in complex regions.
    fillfactor : list
        Fractional limit below which SAAs are rejected. Again, can be given as
        a list so the user can control which SAAs are selected for fitting.
    samplesize : number
        Sample size for randomly selecting SAAs.
    covmethod : string
        Method used to define the coverage. Choices are 'regular' for normal
        scouse fitting or 'random'. The latter generates a random sample of
        'samplesize' SAAs.
    spacing : string
        Method setting spacing of SAAs. Choices are 'nyquist' or 'regular'.
    speccomplexity : string
        Method defining spectral complexity. Choices include:
        - 'momdiff': which measures the difference between the velocity at
                     peak emission and the
                     first moment.
        - 'kurtosis': bases the spectral complexity on the kurtosis of the
                      spectrum.
    totalsaas : number
        Total number of SAAs.
    totalspec : number
        Total number of spectra within the coverage.

    stage 1 - scouse defined attributes
    -----------------------------------
    lenspec : number
        This will refer to the total number of spectra that scouse will actually
        fit. This includes some spectra being fit multiple times due to overlap
        of SAAs if spacing: 'nyquist' is selected.
    saa_dict : dictionary
        A dictionary containing all of the SAA spectra in scouse format
    rms_approx : number
        An estimate of the mean rms across the map
    x : ndarray
        The spectral axis
    xtrim : ndarray
        The spectral axis trimmed according to vel_range (see above)
    trimids : ndarray
        A mask of x according to vel_range

    stage 2 - user defined attributes
    ---------------------------------
    write_ascii : bool
        If True will create an ascii file containing the best-fitting solutions
        to each of the spectral averaging areas.

    stage 2 - scouse defined attributes
    -----------------------------------
    saa_dict : dictionary
        This dictionary houses each of the spectral averaging areas fit by
        scouse
    fitcount : number
        A number indicating how many of the spectra have currently been fit.
        Used so that scouse can remember where it got upto in the fitting
        process
    modelstore : dictionary
        Modelstore contains all the best-fitting solutions while they are
        waiting to be added to saa_dict

    stage 3 - user defined attributes
    ---------------------------------
    tol : list
        Tolerance values for the fitting. Should be in the form
        tol = [T0, T1, T2, T3, T4, T4]. See Henshaw et al. 2016a for full
        explanation but in short:
        T0 = NEW! controls how different the number of components in the fitted
             spectrum can be from the number of components of the parent
             spectrum.
             if |ncomps_spec - ncomps_saa| > T0 ; the fit is rejected
        T1 = multiple of the rms noise value (all components below this
             value are rejected).
             if I_peak < T1*rms ; the component is rejected
        T2 = minimum width of a component (in channels)
             if FHWM < T2*channel_width ; the component is rejected
        T3 = Governs how much the velocity dispersion of a given component can
             differ from the closest matching component in the SAA fit. It is
             given as a multiple of the velocity dispersion of the closest
             matching component.
             relchange = sigma/sigma_saa
             if relchange < 1:
                 relchange = 1/relchange
             if relchange > T3 ; the component is rejected
        T4 = Similar to T3. Governs how much the velocity of a given component
             can differ from the velocity of the closest matching component in
             the parent SAA.
             lowerlim = vel_saa - T4*disp_saa
             upperlim = vel_saa + T4*disp_saa
             if vel < lowerlim or vel > upperlim ; the component is rejected
        T5 = Dictates how close two components have to be before they are
             considered indistinguishable. Given as a multiple of the
             velocity dispersion of the narrowest neighbouring component.
             if vel - vel_neighbour < T5*FWHM_narrowestcomponent ; take the
             average of the two components and use this as a new guess
    njobs : int, optional
        Used for parallelised fitting

    stage 3 - scouse defined attributes
    -----------------------------------
    indiv_dict : dictionary
        A dictionary containing each spectrum fit by scouse and their best
        fitting model solutions

    """

    def __init__(self, config=''):

        # global -- user
        self.config=config
        self.datadirectory=None
        self.filename=None
        self.outputdirectory=None
        self.fittype=None
        self.verbose=None
        self.autosave=None
        # global -- scousepy
        self.cube=None
        self.completed_stages = []

        # stage 1 -- user
        self.write_moments=None
        self.save_fig=None
        # stage 1 -- scousepy coverage
        self.coverage_config_file_path=None
        self.nrefine=None
        self.mask_below=None
        self.x_range=None
        self.y_range=None
        self.vel_range=None
        self.wsaa=None
        self.fillfactor=None
        self.samplesize=None
        self.covmethod=None
        self.spacing=None
        self.speccomplexity=None
        self.totalsaas=None
        self.totalspec=None
        # stage 1 -- scousepy SAAs
        self.lenspec=None
        self.saa_dict=None
        self.rms_approx=None
        self.x=None
        self.xtrim=None
        self.trimids=None
        self.chunk=False

        # stage 2 -- user
        self.alpha=None
        self.snr=None
        self.no_negative=None
        self.write_ascii=None
        # stage 2 -- scousepy
        self.fitcount=None
        self.modelstore={}

        # stage 3 -- user
        self.tol=None
        self.njobs=None

        # stage 5 -- scousepy
        self.check_spec_indices=[]

        # self.stagedirs = []
        # self.cube = None
        # self.config_file=None
        # self.tolerances = None
        # self.specres = None
        # self.fittype = fittype
        # self.sample = None
        # self.x = None
        # self.xtrim = None
        # self.trimids=None
        # self.saa_dict = None
        # self.indiv_dict = None
        # self.key_set = None
        # self.fitcount = None
        #
        # self.fitcounts6 = 0
        # self.blockcount = 0
        # self.blocksize = None
        # self.check_spec_indices = None
        # self.check_block_indices = None
        #

    @staticmethod
    def stage_1(config='', interactive=True, verbose=None, nchunks=None, s1file=None):
        """
        Identify the spatial area over which the fitting will be implemented.

        Parameters
        ----------
        config : string
            Path to the configuration file. This must be provided.
        interactive : bool, optional
            Default is to run coverage with interactive GUI, but this can be
            bypassed in favour of using the config file

        Notes
        -----
        See scouse class documentation for description of the parameters that
        are set during this stage.
        """

        # Import
        from .stage_1 import generate_SAAs, plot_coverage, compute_noise, get_x_axis
        from .io import import_from_config
        from .verbose_output import print_to_terminal
        from scousepy.scousecoverage import ScouseCoverage

        # Check input
        if os.path.exists(config):
            self=scouse(config=config)
            stages=['stage_1']
            for stage in stages:
                import_from_config(self, config, config_key=stage)
        else:
            print('')
            print(colors.fg._lightred_+"Please supply a valid scousepy configuration file. \n\nEither: \n"+
                                  "1: Check the path and re-run. \n"+
                                  "2: Create a configuration file using 'run_setup'."+colors._endc_)
            print('')
            return

        if verbose is not None:
            self.verbose=verbose

        # check if stage 1 has already been run
        if s1file is not None:
            s1path = self.outputdirectory+self.filename+'/stage_1/'+s1file
        else:
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.scousepy'

        if os.path.exists(s1path):
            if self.verbose:
                progress_bar = print_to_terminal(stage='s1', step='load')
            self.load_stage_1(s1path)
            if 's1' in self.completed_stages:
                if self.verbose:
                    print(colors.fg._lightgreen_+"Coverage complete and SAAs initialised. "+colors._endc_)
                    print('')
            return self

        # load the cube
        fitsfile = os.path.join(self.datadirectory, self.filename+'.fits')
        self.load_cube(fitsfile=fitsfile)

        #----------------------------------------------------------------------#
        # Main routine
        #----------------------------------------------------------------------#
        if self.verbose:
            progress_bar = print_to_terminal(stage='s1', step='start')

        # Define the coverage
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            old_log = log.level
            log.setLevel('ERROR')
            # Interactive coverage generator
            coverageobject=ScouseCoverage(scouseobject=self,verbose=self.verbose,
                                            interactive=interactive)
            if interactive:
                 coverageobject.show()
            if coverageobject.config_file is None or len(coverageobject.config_file) == 0:
                raise ValueError("Coverage configuration was set to be 'interactive', but the "
                        "interactive plot window did not wait for input. If you are running in "
                        "Jupyter notebooks or Spyder then try running scouse as a script instead. "
                        "Alternatively set interactive=False and manually update coverage.config.")

            # write out the config file for the coverage
            self.coverage_config_file_path=os.path.join(self.outputdirectory,self.filename,'config_files','coverage.config')
            with open(self.coverage_config_file_path, 'w') as file:
                for line in coverageobject.config_file:
                    file.write(line)
            # set the parameters
            import_from_config(self, self.coverage_config_file_path)
            log.setLevel(old_log)

        # start the time once the coverage has been generated
        starttime = time.time()

        # Create a dictionary to store the SAAs
        self.saa_dict = {}
        # Compute typical noise within the spectra
        self.rms_approx = compute_noise(self)
        # Generate the x axis common to the fitting process
        self.x, self.xtrim, self.trimids = get_x_axis(self)

        # Generate the SAAs
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            old_log = log.level
            log.setLevel('ERROR')
            generate_SAAs(self, coverageobject)
            log.setLevel(old_log)

        # Saving figures
        if self.save_fig:
            coverage_plot_filename=os.path.join(self.outputdirectory,self.filename,'stage_1','coverage.pdf')
            plot_coverage(self, coverageobject, coverage_plot_filename)

        # Write moments as fits files
        if self.write_moments:
            momentoutputdir=os.path.join(self.outputdirectory,self.filename,'stage_1/')
            from .io import output_moments
            output_moments(self.cube.header,coverageobject.moments,momentoutputdir,self.filename)

        if nchunks is not None:
            if np.size(coverageobject.wsaa) > 1:
                raise ValueError("chunking cannot be done for multiple saa sizes. "
                        "Set wsaa to a single size. ")
            else:
                self.chunk=True
                saa_dict_chunks=self.chunk_saas(nchunks)

        # Wrapping up
        plt.close('all')
        endtime = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s1', step='end',
                                             length=np.size(coverageobject.moments[0].value),
                                             t1=starttime, t2=endtime)
        self.completed_stages.append('s1')

        # Save the scouse object automatically
        if self.autosave:
            import pickle
            if nchunks is not None:
                for key in saa_dict_chunks.keys():
                    saa_dict={}
                    saa_dict[0]=saa_dict_chunks[key]
                    with open(self.outputdirectory+self.filename+'/stage_1/s1.'+str(key)+'.scousepy', 'wb') as fh:
                        pickle.dump((self.completed_stages,
                                     self.coverage_config_file_path,
                                     self.lenspec,
                                     saa_dict,
                                     self.x,
                                     self.xtrim,
                                     self.trimids,
                                     self.rms_approx), fh, protocol=proto)
            else:
                if s1file is not None:
                    with open(self.outputdirectory+self.filename+'/stage_1/'+s1file, 'wb') as fh:
                        pickle.dump((self.completed_stages,
                                     self.coverage_config_file_path,
                                     self.lenspec,
                                     self.saa_dict,
                                     self.x,
                                     self.xtrim,
                                     self.trimids,
                                     self.rms_approx), fh, protocol=proto)
                else:
                    with open(self.outputdirectory+self.filename+'/stage_1/s1.scousepy', 'wb') as fh:
                        pickle.dump((self.completed_stages,
                                     self.coverage_config_file_path,
                                     self.lenspec,
                                     self.saa_dict,
                                     self.x,
                                     self.xtrim,
                                     self.trimids,
                                     self.rms_approx), fh, protocol=proto)

        return self

    def load_stage_1(self,fn):
        """
        Method used to load in the progress of stage 1
        """
        import pickle
        with open(fn, 'rb') as fh:
            self.completed_stages,\
            self.coverage_config_file_path,\
            self.lenspec,\
            self.saa_dict,\
            self.x,\
            self.xtrim,\
            self.trimids,\
            self.rms_approx=pickle.load(fh)

    def chunk_saas(self, nchunks):
        """
        Method for dividing saas up into chunks
        """
        saa_dict=self.saa_dict[0]
        totalsaas=np.sum([1 for saakey, saa in saa_dict.items()])
        ntobefit = np.sum([1 if saa.to_be_fit else 0 for saakey, saa in saa_dict.items()])
        nsaasperchunk = np.round(ntobefit/nchunks+0.5)

        saa_dict_chunks={}
        totalcount=0
        for chunk in range(nchunks):
            count=0
            saa_dict_chunk={}
            while count < nsaasperchunk:
                saa_dict_chunk[saa_dict[totalcount].index]=saa_dict[totalcount]
                if saa_dict[totalcount].to_be_fit:
                    count+=1
                    totalcount+=1
                else:
                    totalcount+=1
                if totalcount==totalsaas:
                    break
            saa_dict_chunks[chunk]=saa_dict_chunk
            if totalcount==totalsaas:
                break

        return saa_dict_chunks

    def stage_2(config='', refit=False, verbose=None, s1file=None, s2file=None):
        """
        Fitting of the SAAs

        Parameters
        ----------
        config : string
            Path to the configuration file. This must be provided.

        Notes
        -----
        See scouse class documentation for description of the parameters that
        are set during this stage.

        """
        # import
        from .io import import_from_config
        from .verbose_output import print_to_terminal
        from scousepy.scousefitter import ScouseFitter
        from .model_housing import saamodel
        from .stage_2 import generate_saa_list

        # Check input
        if os.path.exists(config):
            self=scouse(config=config)
            stages=['stage_1','stage_2']
            for stage in stages:
                import_from_config(self, config, config_key=stage)
        else:
            print('')
            print(colors.fg._lightred_+"Please supply a valid scousepy configuration file. \n\nEither: \n"+
                                  "1: Check the path and re-run. \n"+
                                  "2: Create a configuration file using 'run_setup'."+colors._endc_)
            print('')
            return

        if verbose is not None:
            self.verbose=verbose

        # check if stage 1 has already been run
        if s1file is not None:
            s1path = self.outputdirectory+self.filename+'/stage_1/'+s1file
        else:
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.scousepy'

        # check if stage 2 has already been run
        if s2file is not None:
            s2path = self.outputdirectory+self.filename+'/stage_2/'+s2file
        else:
            s2path = self.outputdirectory+self.filename+'/stage_2/s2.scousepy'

        # check if stages 1 and 2 have already been run and load if so
        if os.path.exists(s1path):
            self.load_stage_1(s1path)
            #### TMP FIX
            self.coverage_config_file_path=os.path.join(self.outputdirectory,self.filename,'config_files','coverage.config')
            ###
            import_from_config(self, self.coverage_config_file_path)

        # generate a list of all SAAs (inc. all wsaas)
        # NOTE: this needs to be done before S2 is loaded as it is simply an
        # indexed list - without this the indexing can get messed up during
        # refitting.
        saa_list = generate_saa_list(self)
        saa_list = np.asarray(saa_list)
        if np.shape(saa_list)[0]!=self.totalsaas:
            self.totalsaas=np.shape(saa_list)[0]

        if os.path.exists(s2path):
            if self.verbose:
                progress_bar = print_to_terminal(stage='s2', step='load')
            self.load_stage_2(s2path)
            if self.fitcount is not None:
                if np.all(self.fitcount):
                    if not refit:
                        if self.verbose:
                            print(colors.fg._lightgreen_+"All spectra have solutions. Fitting complete. "+colors._endc_)
                            print('')
                        return self

        # load the cube
        fitsfile = os.path.join(self.datadirectory, self.filename+'.fits')
        self.load_cube(fitsfile=fitsfile)

        #----------------------------------------------------------------------#
        # Main routine
        #----------------------------------------------------------------------#
        if self.verbose:
            progress_bar = print_to_terminal(stage='s2', step='start')

        # Record which spectra have been fit - first check to see if this has
        # already been created
        if self.fitcount is None:
            # if it hasn't
            self.fitcount=np.zeros(int(np.sum(self.totalsaas)), dtype='bool')

        # Default values for SNR and alpha
        if self.snr is None:
            self.snr=3
        if self.alpha is None:
            self.alpha=5

        starttime = time.time()

        fitterobject=ScouseFitter(self.modelstore, method='scouse',
                                spectra=saa_list[:,0],
                                scouseobject=self,
                                fit_dict=self.saa_dict,
                                parent=saa_list[:,1],
                                fitcount=self.fitcount,
                                SNR=self.snr,
                                alpha=self.alpha,
                                no_negative=self.no_negative,
                                refit=refit)
        fitterobject.show()

        if np.all(self.fitcount):
            # Now we want to go through and add the model solutions to the SAAs
            for key in range(len(saa_list[:,0])):
                # identify the right dictionary
                saa_dict=self.saa_dict[saa_list[key,1]]
                # retrieve the SAA
                SAA=saa_dict[saa_list[key,0]]
                # obtain the correct model from modelstore
                modeldict=self.modelstore[key]
                # if there are any zero component fits then mark these as
                # SAA.to_be_fit==False
                if not modeldict['fitconverge']:
                    setattr(SAA, 'to_be_fit', False)
                else:
                    # if it was a zero comp fit but then we changed our minds
                    # set it back again
                    if not SAA.to_be_fit:
                        setattr(SAA, 'to_be_fit', True)
                    # convert the modelstore dictionary into an saamodel object
                    model=saamodel(modeldict)
                    # add this to the SAA
                    SAA.add_saamodel(model)

        # Wrapping up
        endtime = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s2', step='end',
                                             t1=starttime, t2=endtime)

        # Check that the fitting has completed
        if np.all(self.fitcount):
            if self.write_ascii:
                from .io import output_ascii_saa
                output_ascii_saa(self, s2path)
            self.completed_stages.append('s2')

        if self.autosave:
            import pickle
            if s2file is not None:
                with open(self.outputdirectory+self.filename+'/stage_2/'+s2file, 'wb') as fh:
                    pickle.dump((self.completed_stages,
                                self.saa_dict,
                                self.fitcount,
                                self.modelstore), fh, protocol=proto)
            else:
                with open(self.outputdirectory+self.filename+'/stage_2/s2.scousepy', 'wb') as fh:
                    pickle.dump((self.completed_stages,
                                self.saa_dict,
                                self.fitcount,
                                self.modelstore), fh, protocol=proto)

        return self

    def load_stage_2(self, fn):
        import pickle
        with open(fn, 'rb') as fh:
            self.completed_stages,\
            self.saa_dict, \
            self.fitcount, \
            self.modelstore = pickle.load(fh)

    def stage_3(config='', verbose=None, s1file=None, s2file=None, s3file=None):
        """
        Stage 3

        Automated fitting of the data.

        Parameters
        ----------
        config : string
            Path to the configuration file. This must be provided.

        """
        # import
        from .io import import_from_config
        from .verbose_output import print_to_terminal

        # Check input
        if os.path.exists(config):
            self=scouse(config=config)
            stages=['stage_1','stage_2','stage_3']
            for stage in stages:
                import_from_config(self, config, config_key=stage)
        else:
            print('')
            print(colors.fg._lightred_+"Please supply a valid scousepy configuration file. \n\nEither: \n"+
                                  "1: Check the path and re-run. \n"+
                                  "2: Create a configuration file using 'run_setup'."+colors._endc_)
            print('')
            return

        if verbose is not None:
            self.verbose=verbose

        # check if stage 1 has already been run
        if s1file is not None:
            s1path = self.outputdirectory+self.filename+'/stage_1/'+s1file
        else:
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.scousepy'

        # check if stage 2 has already been run
        if s2file is not None:
            s2path = self.outputdirectory+self.filename+'/stage_2/'+s2file
        else:
            s2path = self.outputdirectory+self.filename+'/stage_2/s2.scousepy'

        # check if stage 3 has already been run
        if s3file is not None:
            s3path = self.outputdirectory+self.filename+'/stage_3/'+s3file
        else:
            s3path = self.outputdirectory+self.filename+'/stage_3/s3.scousepy'

        # check if stages 1, 2, and 3 have already been run and load if so
        if os.path.exists(s1path):
            self.load_stage_1(s1path)
            #### TMP FIX
            self.coverage_config_file_path=os.path.join(self.outputdirectory,self.filename,'config_files','coverage.config')
            ###
            import_from_config(self, self.coverage_config_file_path)

        if os.path.exists(s2path):
            self.load_stage_2(s2path)
            if self.fitcount is not None:
                if not np.all(self.fitcount):
                    print(colors.fg._lightred_+"Not all spectra have solutions. Please complete stage 2 before proceding. "+colors._endc_)
                    return

        if os.path.exists(s3path):
            if self.verbose:
                progress_bar = print_to_terminal(stage='s3', step='load')
            self.load_stage_3(s3path)
            if 's3' in self.completed_stages:
                if self.verbose:
                    print(colors.fg._lightgreen_+"Fitting completed. "+colors._endc_)
                    print('')
            return self


        # load the cube
        fitsfile = os.path.join(self.datadirectory, self.filename+'.fits')
        self.load_cube(fitsfile=fitsfile)

        #----------------------------------------------------------------------#
        # Main routine
        #----------------------------------------------------------------------#
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='start')

        starttime = time.time()
        # create a list that is going to house all instances of the
        # individual_spectrum class. We want this to be a list for ease of
        # parallelisation.
        starttimeinit=time.time()
        indivspec_list=initialise_fitting(self)
        endtimeinit=time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='initend',t1=starttimeinit, t2=endtimeinit)

        # determine cpus to use
        if self.njobs==None:
            self.get_njobs()

        # now begin the fitting
        starttimefitting=time.time()
        indivspec_list_completed=autonomous_decomposition(self, indivspec_list)
        endtimefitting=time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='fitend',
                                        t1=starttimefitting, t2=endtimefitting)

        # now compile the spectra
        starttimecompile=time.time()
        compile_spectra(self, indivspec_list_completed)
        endtimecompile=time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='compileend',
                                        t1=starttimecompile, t2=endtimecompile)

        # model selection
        starttimemodelselection = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='modelselectstart')
        # select the best model out of those available - i.e. that with the
        # lowest aic value
        model_selection(self)
        endtimemodelselection = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='modelselectend',
                        t1=starttimemodelselection, t2=endtimemodelselection)

        # Wrapping up
        endtime = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s3', step='end',
                                             t1=starttime, t2=endtime)

        self.completed_stages.append('s3')

        # Save the scouse object automatically
        if self.autosave:
            import pickle
            if s3file is not None:
                if os.path.exists(self.outputdirectory+self.filename+'/stage_3/'+s3file):
                    os.rename(self.outputdirectory+self.filename+'/stage_3/'+s3file,self.outputdirectory+self.filename+'/stage_3/'+s3file+'.bk')

                with open(self.outputdirectory+self.filename+'/stage_3/'+s3file, 'wb') as fh:
                    pickle.dump((self.completed_stages, self.indiv_dict), fh, protocol=proto)
            else:
                if os.path.exists(self.outputdirectory+self.filename+'/stage_3/s3.scousepy'):
                    os.rename(self.outputdirectory+self.filename+'/stage_3/s3.scousepy',self.outputdirectory+self.filename+'/stage_3/s3.scousepy.bk')

                with open(self.outputdirectory+self.filename+'/stage_3/s3.scousepy', 'wb') as fh:
                    pickle.dump((self.completed_stages, self.indiv_dict), fh, protocol=proto)

        return self

    def load_stage_3(self, fn):
        import pickle
        with open(fn, 'rb') as fh:
            self.completed_stages,\
            self.indiv_dict = pickle.load(fh)

    def stage_4(config='', bitesize=False, verbose=None, nocheck=False,
                s1file = None, s2file = None, s3file=None, s4file=None,
                scouseobjectalt=[]):
        """
        Stage 4

        In this stage the user is required to check the best-fitting solutions

        """
        # import
        from .io import import_from_config
        from .verbose_output import print_to_terminal
        from scousepy.scousefitchecker import ScouseFitChecker

        # Check input
        if os.path.exists(config):
            self=scouse(config=config)
            stages=['stage_1','stage_2','stage_3']
            for stage in stages:
                import_from_config(self, config, config_key=stage)
        else:
            print('')
            print(colors.fg._lightred_+"Please supply a valid scousepy configuration file. \n\nEither: \n"+
                                  "1: Check the path and re-run. \n"+
                                  "2: Create a configuration file using 'run_setup'."+colors._endc_)
            print('')
            return

        if verbose is not None:
            self.verbose=verbose

        # check if stage 1 has already been run
        if s1file is not None:
            s1path = self.outputdirectory+self.filename+'/stage_1/'+s1file
        else:
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.scousepy'

        # check if stage 2 has already been run
        if s2file is not None:
            s2path = self.outputdirectory+self.filename+'/stage_2/'+s2file
        else:
            s2path = self.outputdirectory+self.filename+'/stage_2/s2.scousepy'

        # check if stage 3 has already been run
        if s3file is not None:
            s3path = self.outputdirectory+self.filename+'/stage_3/'+s3file
        else:
            s3path = self.outputdirectory+self.filename+'/stage_3/s3.scousepy'

        if s4file is not None:
            s4path = self.outputdirectory+self.filename+'/stage_4/'+s4file
        else:
            s4path = self.outputdirectory+self.filename+'/stage_4/s4.scousepy'


        # check if stages 1, 2, 3 and 4 have already been run
        if os.path.exists(s1path):
            self.load_stage_1(s1path)
            #### TMP FIX
            self.coverage_config_file_path=os.path.join(self.outputdirectory,self.filename,'config_files','coverage.config')
            ###
            import_from_config(self, self.coverage_config_file_path)
        if os.path.exists(s2path):
            self.load_stage_2(s2path)
            if self.fitcount is not None:
                if not np.all(self.fitcount):
                    print(colors.fg._lightred_+"Not all spectra have solutions. Please complete stage 2 before proceding. "+colors._endc_)
                    return

        if os.path.exists(s3path):
            self.load_stage_3(s3path)

        if os.path.exists(s4path):
            if self.verbose:
                progress_bar = print_to_terminal(stage='s4', step='load')
            self.load_stage_4(s4path)
            if not bitesize:
                if self.verbose:
                    print(colors.fg._lightgreen_+"Fit check already complete. Use bitesize=True to re-enter model checker. "+colors._endc_)
                    print('')
                return self

        # load the cube
        fitsfile = os.path.join(self.datadirectory, self.filename+'.fits')
        self.load_cube(fitsfile=fitsfile)

        #----------------------------------------------------------------------#
        # Main routine
        #----------------------------------------------------------------------#

        starttime = time.time()

        if np.size(self.check_spec_indices)==0:
            if verbose:
                 progress_bar = print_to_terminal(stage='s4', step='start')

        # Interactive coverage generator
        fitcheckerobject=ScouseFitChecker(scouseobject=self, selected_spectra=self.check_spec_indices, scouseobjectalt=scouseobjectalt)
        if not nocheck:
            fitcheckerobject.show()
        else:
            fitcheckerobject.close_window()

        if bitesize:
            self.check_spec_indices=self.check_spec_indices+fitcheckerobject.check_spec_indices
            self.check_spec_indices=list(set(self.check_spec_indices))
        else:
            self.check_spec_indices=fitcheckerobject.check_spec_indices

        # for key in self.indiv_dict.keys():
        #     print(key, self.indiv_dict[key])

        # print('')

        sorteddict={}
        for sortedkey in sorted(self.indiv_dict.keys()):
            sorteddict[sortedkey]=self.indiv_dict[sortedkey]

        self.indiv_dict=sorteddict

        # for key in self.indiv_dict.keys():
        #     print(key, self.indiv_dict[key])

        # print('')

        # Wrapping up
        endtime = time.time()
        if self.verbose:
            progress_bar = print_to_terminal(stage='s4', step='end',
                                             t1=starttime, t2=endtime,
                                             var=self.check_spec_indices)

        self.completed_stages.append('s4')

        # Save the scouse object automatically
        if self.autosave:
            import pickle
            if s4file is not None:
                if os.path.exists(self.outputdirectory+self.filename+'/stage_4/'+s4file):
                    os.rename(self.outputdirectory+self.filename+'/stage_4/'+s4file,self.outputdirectory+self.filename+'/stage_4/'+s4file+'.bk')

                with open(self.outputdirectory+self.filename+'/stage_4/'+s4file, 'wb') as fh:
                    pickle.dump((self.completed_stages,self.check_spec_indices,self.indiv_dict), fh, protocol=proto)
            else:
                if os.path.exists(self.outputdirectory+self.filename+'/stage_4/s4.scousepy'):
                    os.rename(self.outputdirectory+self.filename+'/stage_4/s4.scousepy',self.outputdirectory+self.filename+'/stage_4/s4.scousepy.bk')

                with open(self.outputdirectory+self.filename+'/stage_4/s4.scousepy', 'wb') as fh:
                    pickle.dump((self.completed_stages,self.check_spec_indices,self.indiv_dict), fh, protocol=proto)

        return self

    def load_stage_4(self, fn):
        import pickle
        with open(fn, 'rb') as fh:
            self.completed_stages, self.check_spec_indices, self.indiv_dict = pickle.load(fh)

#==============================================================================#
# io
#==============================================================================#

    def run_setup(filename, datadirectory, outputdir=None, description=True,
                  verbose=True):
        """
        Generates a scousepy configuration file

        Parameters
        ----------
        filename : string
            Name of the file to be loaded
        datadirectory : string
            Directory containing the datacube
        outputdir : string, optional
            Alternate output directory. Deflault is datadirectory
        description : bool, optional
            whether or not a description of each parameter is included in the
            configuration file
        verbose : bool, optional
            verbose output to terminal
        """
        from .io import create_directory_structure
        from .io import generate_config_file
        from .verbose_output import print_to_terminal

        if outputdir is None:
            outputdir=datadirectory

        config_filename='scousepy.config'
        config_filename_coverage='coverage.config'

        scousedir=os.path.join(outputdir, filename)
        configdir=os.path.join(scousedir+'/config_files')
        configpath=os.path.join(scousedir+'/config_files', config_filename)
        configpath_coverage=os.path.join(scousedir+'/config_files', config_filename_coverage)

        if verbose:
            progress_bar = print_to_terminal(stage='init', step='init')

        if os.path.exists(configpath):
            if verbose:
                progress_bar = print_to_terminal(stage='init', step='configexists')
            return os.path.join(scousedir+'/config_files', config_filename)
        else:
            if not os.path.exists(scousedir):
                create_directory_structure(scousedir)
                generate_config_file(filename, datadirectory, outputdir, configdir, config_filename, description)
                generate_config_file(filename, datadirectory, outputdir, configdir, config_filename_coverage, description, coverage=True)
                if verbose:
                    progress_bar = print_to_terminal(stage='init', step='makingconfig')
            else:
                configpath=None
                print('')
                print(colors.fg._yellow_+"Warning: output directory exists but does not contain a config file. "+colors._endc_)
                print('')

        return configpath

    def load_cube(self, fitsfile=None, cube=None):
        """
        Load in a cube

        Parameters
        ----------
        fitsfile : fits
            File in fits format to be read in
        cube : spectral cube
            If fits file is not supplied - provide a spectral cube object
            instead

        """
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            old_log = log.level
            log.setLevel('ERROR')

            # Read in the datacube
            if cube is None:
                _cube = SpectralCube.read(fitsfile).with_spectral_unit(u.km/u.s,
                                                    velocity_convention='radio')
            else:
                _cube = cube

            if _cube.spectral_axis.diff()[0] < 0:
                if np.abs(_cube.spectral_axis[0].value -
                                    _cube[::-1].spectral_axis[-1].value) > 1e-5:
                    raise ImportError("Update to a more recent version of "
                                      "spectral-cube or reverse the axes "
                                      "manually.")
                _cube = _cube[::-1]

            self.cube = _cube
            log.setLevel(old_log)

        return _cube

    def save_to(self, filename):
        """
        Saves an output file
        """
        from .io import save
        return save(self, filename)

    @staticmethod
    def load_from(filename):
        """
        Loads a previously computed scousepy file
        """
        from .io import load
        return load(filename)

#==============================================================================#
# Methods
#==============================================================================#

    def get_njobs(self):
        """
        Determines number of cpus available for parallel processing. If njobs
        is set to None scouse will automatically use 75% of available cpus.
        """
        import multiprocessing
        maxcpus=multiprocessing.cpu_count()
        self.njobs=int(0.75*maxcpus)

#==============================================================================#
# Analysis
#==============================================================================#
    @staticmethod
    def compute_stats(self, filepath=None):
        """
        Computes some statistics for the fitting process
        """
        from .statistics import stats
        # load the cube
        if filepath is None:
            fitsfile = os.path.join(self.datadirectory, self.filename+'.fits')
        else:
            fitsfile = filepath
        self.load_cube(fitsfile=fitsfile)

        return stats(scouseobject=self)

    @staticmethod
    def combine_chunks(config='', nchunks=None, s1file=None, s2file=None):
        from .io import import_from_config
        from .verbose_output import print_to_terminal
        from .stage_2 import generate_saa_list

        # Check input
        if os.path.exists(config):
            self=scouse(config=config)
            stages=['stage_1']
            for stage in stages:
                import_from_config(self, config, config_key=stage)
        else:
            print('')
            print(colors.fg._lightred_+"Please supply a valid scousepy configuration file. \n\nEither: \n"+
                                  "1: Check the path and re-run. \n"+
                                  "2: Create a configuration file using 'run_setup'."+colors._endc_)
            print('')
            return

        # begin by loading the first chunks
        s1path0 = self.outputdirectory+self.filename+'/stage_1/s1.1.scousepy'

        if os.path.exists(s1path0):
            if self.verbose:
                progress_bar = print_to_terminal(stage='s1', step='load')
            self.load_stage_1(s1path0)
            #### TMP FIX
            self.coverage_config_file_path=os.path.join(self.outputdirectory,self.filename,'config_files','coverage.config')
            ###
            import_from_config(self, self.coverage_config_file_path)
        else:
            print('')
            print(colors.fg._lightred_+"It looks like the S1 chunks are missing. \n\n"+
                                       "Make sure they are located in the stage_1 directory and have the naming convention s1.nchunk.scousepy."+colors._endc_)
            print('')
            return

        saa_dicts1={}
        saa_dicts1[0]={}

        if self.verbose:
            print(colors.fg._lightgreen_+"Combining the chunks into a single dictionary..."+colors._endc_)
            print('')

        # save a combined s1 first
        for chunk in range(nchunks):
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.'+str(chunk)+'.scousepy'
            s2path = self.outputdirectory+self.filename+'/stage_2/s2.'+str(chunk)+'.scousepy'
            if os.path.exists(s1path):
                self.load_stage_1(s1path)
                for key, saa in self.saa_dict[0].items():
                    saa_dicts1[0][key]=saa

        self.saa_dict=saa_dicts1

        import pickle
        if s1file is not None:
            with open(self.outputdirectory+self.filename+'/stage_1/'+s1file, 'wb') as fh:
                pickle.dump((self.completed_stages,
                             self.coverage_config_file_path,
                             self.lenspec,
                             self.saa_dict,
                             self.x,
                             self.xtrim,
                             self.trimids,
                             self.rms_approx), fh, protocol=proto)
        else:
            with open(self.outputdirectory+self.filename+'/stage_1/s1.combine.scousepy', 'wb') as fh:
                pickle.dump((self.completed_stages,
                             self.coverage_config_file_path,
                             self.lenspec,
                             self.saa_dict,
                             self.x,
                             self.xtrim,
                             self.trimids,
                             self.rms_approx), fh, protocol=proto)


        # save a combined s2 next
        saa_dicts2={}
        saa_dicts2[0]={}
        modelstore={}
        for chunk in range(nchunks):
            s1path = self.outputdirectory+self.filename+'/stage_1/s1.'+str(chunk)+'.scousepy'
            s2path = self.outputdirectory+self.filename+'/stage_2/s2.'+str(chunk)+'.scousepy'
            if os.path.exists(s1path):
                self.load_stage_1(s1path)
                if os.path.exists(s2path):
                    self.load_stage_2(s2path)
                    if self.fitcount is not None:
                        if not np.all(self.fitcount):
                            print('')
                            print(colors.fg._lightred_+"Fitting is incomplete for chunk "+str(chunk)+". \n\n"+
                                                       "Please complete the fitting prior to combining the chunks."+colors._endc_)
                            print('')
                            return
                        else:
                            to_be_fit_count=0
                            for key, saa in self.saa_dict[0].items():

                                saas1=saa_dicts1[0][key]

                                if saa.to_be_fit:
                                    keysms=list(modelstore.keys())
                                    if np.size(keysms)==0:
                                        keyms=0
                                    else:
                                        keyms=np.max(keysms)+1
                                    modelstore[keyms]=self.modelstore[to_be_fit_count]
                                    to_be_fit_count+=1
                                elif not (saa.to_be_fit) and (saas1.to_be_fit):
                                    keysms=list(modelstore.keys())
                                    if np.size(keysms)==0:
                                        keyms=0
                                    else:
                                        keyms=np.max(keysms)+1
                                    modelstore[keyms]=self.modelstore[to_be_fit_count]

                                    if self.modelstore[to_be_fit_count]['fitconverge']:
                                        setattr(saa, 'to_be_fit', True)
                                    to_be_fit_count+=1
                                else:
                                    pass

                                saa_dicts2[0][key]=saa

            else:
                print('')
                print(colors.fg._lightred_+"Chunk "+str(chunk)+" appears to be missing. \n\n"+
                                           "Please make sure it is located in the stage_1 directory."+colors._endc_)
                print('')

        self.saa_dict=saa_dicts2
        self.modelstore=modelstore
        self.fitcount=np.ones(np.size(list(self.modelstore.keys())), dtype='bool')

        if s2file is not None:
            with open(self.outputdirectory+self.filename+'/stage_2/'+s2file, 'wb') as fh:
                pickle.dump((self.completed_stages,
                            self.saa_dict,
                            self.fitcount,
                            self.modelstore), fh, protocol=proto)
        else:
            with open(self.outputdirectory+self.filename+'/stage_2/s2.combine.scousepy', 'wb') as fh:
                pickle.dump((self.completed_stages,
                            self.saa_dict,
                            self.fitcount,
                            self.modelstore), fh, protocol=proto)

        return self

    def combine(scouseobjects=[]):
        """
        Combines multiple s3 decomposition runs into a single output file.

        Parameters
        ----------
        scouseobjects : list
            A list of scousepy objects that have been loaded via the load_stage_3
            command.

        Output
        ------
        scouseobject : an instance of the scousepy class
            A new scouseobject where the s3 stages have been merged and best
            fitting solutions combined into a single indiv_dict
        """
        # create an empty dictionary that will house the combined results
        indiv_dict_combine={}
        # get the individual dictionaries
        indiv_dicts=[scouseobject.indiv_dict for scouseobject in scouseobjects]
        # identify the maximum index in each dict for mismatched inputs
        maxindexes=[max(indiv_dict) for indiv_dict in indiv_dicts]
        # get the id where the maximum index is located
        idmax=np.squeeze(np.where(maxindexes==np.max(maxindexes)))
        # get the maximum of these
        maxindex=np.max(maxindexes)
        # we are going to loop over the indexes
        for key in range(0,maxindex+1):
            keycheck=[True if key in indiv_dict else False for indiv_dict in indiv_dicts]
            if np.any(keycheck):
                # if only one key is found we are going to add this to the new
                # dictionary directly
                if np.sum(keycheck)==1:
                    # get the index of the dictionary where the key is found
                    idx=np.squeeze(np.where(keycheck))
                    # get the individual spectrum
                    indivspec=indiv_dicts[idx][key]
                    # now we are going to add an attribute to the spectrum to
                    # indicate which dictionary it came from
                    setattr(indivspec,'combine',idx)
                    # now add this to the new dictionary
                    indiv_dict_combine[key]=indivspec
                else:
                    # if key is found in more than one of our dictionaries then
                    # we have a decision to make

                    # get the indices of the dictionaries where the key is found
                    idx=np.squeeze(np.where(keycheck))
                    # get the individual spectra
                    indivspecs=[indiv_dicts[id][key] for id in idx]
                    # get the models and the AIC values
                    models=[indivspec.model for indivspec in indivspecs]
                    aic=[indivspec.model.AIC for indivspec in indivspecs]

                    # get the min aic
                    idx_aic = np.squeeze(np.where(aic == np.min(aic)))
                    minaic=aic[idx_aic]
                    minaicmodel=models[idx_aic]
                    # get a list of the models without the model with the minimum aic
                    models_without_minaicmodel=[model for j,model in enumerate(models) if j!=idx_aic]
                    aic_without_minaic=[aic_ for j, aic_ in enumerate(aic) if j!=idx_aic]

                    # compute the difference in AIC between the selected model
                    # and the rest
                    delta_aic=[(aic_ - minaic) for aic_ in aic_without_minaic]
                    # find the smallest delta value as all others can be discarded
                    idx_delta=np.squeeze(np.where(delta_aic == np.min(delta_aic)))
                    # get the model with the minimum delta value
                    mindeltamodel=models_without_minaicmodel[idx_delta]
                    mindelta=delta_aic[idx_delta]

                    # model selection criteria
                    if mindelta < 2.0:
                        # if there are any models within mindelta < 2 of the
                        # min aic value, we penelise the min aic model and
                        # select the one with the smallest delta to it. Most
                        # often this will favour models with a fewer number of
                        # free parameters.

                        # this will likely only happen in a few cases
                        bfmodel=mindeltamodel
                    else:
                        # retain the model with the lowest aic value
                        bfmodel=minaicmodel

                    # identify which model our new best-fitting model relates to
                    when_true = [model==bfmodel for model in models]
                    idx_model=np.squeeze(np.where(when_true))
                    # set this to be the default spectrum
                    indivspec=indivspecs[idx_model]
                    # now we are going to add an attribute to the spectrum to
                    # indicate which dictionary it came from
                    setattr(indivspec,'combine',idx_model)
                    # now double check to see if any of the other models are
                    # already contained within the model list in indiv spec
                    when_true = [model_!=model for model_ in models for model in indivspec.model_from_parent]
                    # if there are any models which are not duplicated in the list
                    # we are going to add these to the list
                    if np.any(when_true):
                        # remove all duplicated models from the model list
                        models_without_duplicates=[model for j,model in enumerate(models) if when_true[j] and model!=bfmodel]
                        for model in models_without_duplicates:
                            # add these to indivspec
                            indivspec.model_from_parent.append(model)
                    # now add this to the new dictionary
                    indiv_dict_combine[key]=indivspec

        # we now have a dictionary containing the best fitting solutions across
        # multiple versions of the decompositions. We now want to output this
        # as something sensible.

        # lets create a safe copy of the decomposition which contains the most
        # fitted spectra
        s3template=scouseobjects[0]
        # copy
        import copy
        s3copy=copy.deepcopy(s3template)
        # update the dictionary with the new fits
        setattr(s3copy,'indiv_dict',indiv_dict_combine)
        # save as a new file
        import pickle
        with open(s3copy.outputdirectory+s3copy.filename+'/stage_3/s3.scousepy.combined', 'wb') as fh:
            pickle.dump((s3copy.completed_stages, s3copy.indiv_dict), fh, protocol=proto)

        return s3copy
