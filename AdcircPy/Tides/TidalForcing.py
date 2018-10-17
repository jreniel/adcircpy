from collections import OrderedDict
from datetime import datetime, timedelta
import os
import calendar
import numpy as np
from AdcircPy import core
from AdcircPy.Tides import orbital_constants


class TidalForcing(OrderedDict):
  """
  This class initializes tidal forcings information required to
  run some tidal models.
  Note:
    TPXO initializations is not part of TidalForcing because
    it depends on the mesh boundaries, therefore TPXO initialization
    is called on the _AdcircRun class.
  """
  def __init__(self, start_date, end_date, spinup_date=None, constituents=None):
    self.constituents = constituents
    self.start_date   = start_date
    self.end_date     = end_date
    self.spinup_date  = spinup_date
    self.cachedir     = core.get_cache_dir()
    self.tpxo_path    = self.cachedir + "/h_tpxo9.v1.nc"
    self.default_constituents = ['Mm', 'Mf', 'Q1',  'O1', 'P1',
                                 'S1', 'K1', '2N2', 'N2', 'M2',
                                 'S2', 'K2', 'MN4', 'M4', 'MS4']
    self._init_dates()
    self._init_constituent_dictionary()
    self._init_orbital_params()
    self._init_node_factors()

  @property
  def units(self):
    return 'rad/sec'
    
  def __check_start_date(self):
    if isinstance(self.start_date, datetime)==False:
      raise IOError("start_date must be a datetime.datetime instance.")
  
  def __check_end_date(self):
    if isinstance(self.end_date, datetime)==False:
      raise IOError("end_date must be a datetime.datetime instance.")
    elif self.end_date<=self.start_date:
        raise Exception('end_date must be larger than start_date.')

  def __check_spinup_date(self):
    if self.spinup_date is None:
      self.spinup_date = self.start_date - timedelta(days=15)
    else:
      if isinstance(self.spinup_date, datetime)==False:
        raise IOError("spinup_date must be a datetime.datetime instance.")
      elif self.spinup_date>=self.start_date:
        raise Exception('spinup_date must be smaller than start_date.')

  def _init_dates(self):
    self.__check_start_date()
    self.__check_end_date()
    self.__check_spinup_date()

  def _init_constituent_dictionary(self):
    if self.constituents is not None:
      self.constituents = list(self.constituents)
      for constituent in self.constituents:
        if constituent not in self.default_constituents:
          raise Exception('\nUnknown Tidal Constituent \'{}\'.\n'.format(constituent)+\
                          'Possible constituents are: {} '.format(self.default_constituents))
    else:
      # These are the only ones available in TPXO, so we're limited to these.
      self.constituents = self.default_constituents
      # self.constituents = OrderedDict(sorted(orbital_constants.orbital_frequency.items(), key=lambda x: x[1]))
    for constituent in self.constituents:
      self[constituent] = dict()
      self[constituent]['orbital_frequency'] = orbital_constants.orbital_frequency[constituent]
      if constituent in orbital_constants.doodson_coefficient.keys():
        self[constituent]['doodson_coefficient'] = orbital_constants.doodson_coefficient[constituent]
      if constituent in orbital_constants.tidal_potential_amplitude.keys():
        self[constituent]['tidal_potential_amplitude'] = orbital_constants.tidal_potential_amplitude[constituent]
      if constituent in orbital_constants.earth_tidal_potential_reduction_factor.keys():
        self[constituent]['earth_tidal_potential_reduction_factor'] = orbital_constants.earth_tidal_potential_reduction_factor[constituent]


  def _init_orbital_params(self):
    self.DYR  = self.spinup_date.year - 1900. 
    self.DDAY = self.spinup_date.timetuple().tm_yday + int((self.spinup_date.year-1901.)/4.)-1
    self.hour_middle = self.spinup_date.hour + ((self.end_date - self.spinup_date).total_seconds()/3600)/2
    self.DN   = self._get_lunar_node(self.hour_middle)
    self.N    = np.deg2rad(self.DN)
    self.DP   = self._get_lunar_perigee(self.hour_middle)
    self.P    = np.deg2rad(self.DP)
    self.DH   = self._get_solar_mean_longitude(self.spinup_date.hour)
    self.H    = np.deg2rad(self.DH)
    self.DS   = self._get_lunar_mean_longitude(self.spinup_date.hour)
    self.S    = np.deg2rad(self.DS)
    self.DP1  = self._get_solar_perigee(self.spinup_date.hour)
    self.P1   = np.deg2rad(self.DP1)
    self.I    = np.arccos(.9136949-.0356926*np.cos(self.N))
    self.DI   = np.rad2deg(self.I)
    self.NU   = np.arcsin(.0897056*np.sin(self.N)/np.sin(self.I))
    self.DNU  = np.rad2deg(self.NU)
    self.XI   = self.N-2.*np.arctan(.64412*np.tan(self.N/2)) - self.NU
    self.DXI  = np.rad2deg(self.XI)
    self.DT   = (180.+self.spinup_date.hour*(360./24)) % 360.
    self.T    = np.deg2rad(self.DT)
    self.NUP  = np.arctan(np.sin(self.NU)/(np.cos(self.NU)+.334766/np.sin(2.*self.I)))
    self.DNUP = np.rad2deg(self.NUP)
    self.DPC  = (self.DP - self.DXI) % 360.
    self.PC   = np.deg2rad(self.DPC)
    self.R    = np.arctan(np.sin(2.*self.PC)/((1./6.)*(1./np.tan(.5*self.I))**2-np.cos(2.*self.PC)))
    self.DR   = np.rad2deg(self.R)
    self.NUP2 = np.arctan(np.sin(2.*self.NU)/(np.cos(2.*self.NU)+.0726184/np.sin(self.I)**2))/2.
    self.DNUP2 = np.rad2deg(self.NUP2)
    self.Q    = np.arctan2((5.*np.cos(self.I)-1.)*np.sin(self.PC), (7.*np.cos(self.I)+1.)*np.cos(self.PC))
    self.DQ   = np.rad2deg(self.Q)

  def _init_node_factors(self):
    for constituent in self.keys():
      # nodal factors are referenced to middle of record
      self[constituent]["nodal_factor"] = self._get_nodal_factor(constituent)
      # greenwich terms are referenced to the spinup_date
      self[constituent]["greenwich_term"] = (self._get_greenwich_term(constituent)) % 360.

  def _get_lunar_node(self, hours):
    """ """
    return (259.1560564-19.328185764*self.DYR-.0529539336*self.DDAY-.0022064139*hours) % 360.

  def _get_lunar_perigee(self, hours):
    """ """
    return (334.3837214+40.66246584*self.DYR+.111404016*self.DDAY+.004641834*hours) % 360.

  def _get_lunar_mean_longitude(self, hours):
    """ """
    return (277.0256206+129.38482032*self.DYR+13.176396768*self.DDAY+.549016532*hours) % 360.

  def _get_solar_perigee(self, hours):
    """ """
    return (281.2208569+.01717836*self.DYR+.000047064*self.DDAY+.000001961*hours) % 360.

  def _get_solar_mean_longitude(self, hours):
    """ """
    return (280.1895014-.238724988*self.DYR+.9856473288*self.DDAY+.0410686387*hours) % 360.

  def _get_nodal_factor(self, constituent):
    """ """
    if constituent   == "M2":
      return self._EQ78()
    elif constituent == "S2":
      return 1.0
    elif constituent == "N2":
      return self._EQ78()
    elif constituent == "K1":
      return self._EQ227()
    elif constituent == "M4":
      return (self._EQ78())**2.
    elif constituent == "O1":
      return self._EQ75()
    elif constituent == "M6":
      return (self._EQ78())**3.
    elif constituent == "MK3":
      return self._EQ78()*self._EQ227()
    elif constituent == "S4":
      return 1.0
    elif constituent == "MN4":
      return (self._EQ78())**2.
    elif constituent == "Nu2":
      return self._EQ78()
    elif constituent == "S6":
      return 1.0
    elif constituent == "MU2":
      return self._EQ78()
    elif constituent == "2N2":
      return self._EQ78()
    elif constituent == "OO1":
      return self._EQ77()
    elif constituent == "lambda2":
      return self._EQ78()
    elif constituent == "S1":
      return 1.0
    elif constituent == "M1":
      return self._EQ207()
    elif constituent == "J1":
      return self._EQ76()
    elif constituent == "Mm":
      return self._EQ73()
    elif constituent == "Ssa":
      return 1.0
    elif constituent == "Sa":
      return 1.0
    elif constituent == "Msf":
      return self._EQ78()
    elif constituent == "Mf":
      return self._EQ74()
    elif constituent == "RHO":
      return self._EQ75()
    elif constituent == "Q1":
      return self._EQ75()
    elif constituent == "T2":
      return 1.0
    elif constituent == "R2":
      return 1.0
    elif constituent == "2Q1":
      return self._EQ75()
    elif constituent == "P1":
      return 1.0
    elif constituent == "2SM2":
      return self._EQ78()
    elif constituent == "M3":
      return self._EQ149()
    elif constituent == "L2":
      return self._EQ215()
    elif constituent == "2MK3":
      return  self._EQ227()*self._EQ78()**2
    elif constituent == "K2":
      return self._EQ235()
    elif constituent == "M8":
      return self._EQ78()**4
    elif constituent == "MS4":
      return self._EQ78()

  def _get_greenwich_term(self, constituent):
    """ """
    if constituent   == "M2":
      return 2.*(self.DT-self.DS+self.DH)+2.*(self.DXI-self.DNU)
    elif constituent == "S2":
      return 2.*self.DT
    elif constituent == "N2":
      return 2.*(self.DT+self.DH)-3.*self.DS+self.DP+2.*(self.DXI-self.DNU)
    elif constituent == "K1":
      return self.DT+self.DH-90.-self.DNUP
    elif constituent == "M4":
      return 4.*(self.DT-self.DS+self.DH)+4.*(self.DXI-self.DNU)
    elif constituent == "O1":
      return self.DT-2.*self.DS+self.DH+90.+2.*self.DXI-self.DNU
    elif constituent == "M6":
      return 6.*(self.DT-self.DS+self.DH)+6.*(self.DXI-self.DNU)
    elif constituent == "MK3":
      return 3.*(self.DT+self.DH)-2.*self.DS-90.+2.*(self.DXI-self.DNU)-self.DNUP
    elif constituent == "S4":
      return 4.*self.DT
    elif constituent == "MN4":
      return 4.*(self.DT+self.DH)-5.*self.DS+self.DP+4.*(self.DXI-self.DNU)
    elif constituent == "Nu2":
      return 2.*self.DT-3.*self.DS+4.*self.DH-self.DP+2.*(self.DXI-self.DNU)
    elif constituent == "S6":
      return 6.*self.DT
    elif constituent == "MU2":
      return 2.*(self.DT+2.*(self.DH-self.DS))+2.*(self.DXI-self.DNU)
    elif constituent == "2N2":
      return 2.*(self.DT-2.*self.DS+self.DH+self.DP)+2.*(self.DXI-self.DNU)
    elif constituent == "OO1":
      return self.DT+2.*self.DS+self.DH-90.-2.*self.DXI-self.DNU
    elif constituent == "lambda2":
      return 2.*self.DT-self.DS+self.DP+180.+2.*(self.DXI-self.DNU)
    elif constituent == "S1":
      return self.DT
    elif constituent == "M1":
      return self.DT-self.DS+self.DH-90.+self.DXI-self.DNU+self.DQ
    elif constituent == "J1":
      return self.DT+self.DS+self.DH-self.DP-90.-self.DNU
    elif constituent == "Mm":
      return self.DS-self.DP
    elif constituent == "Ssa":
      return 2.*self.DH
    elif constituent == "Sa":
      return self.DH
    elif constituent == "Msf":
      return 2.*(self.DS-self.DH)
    elif constituent == "Mf":
      return 2.*self.DS-2.*self.DXI
    elif constituent == "RHO":
      return self.DT+3.*(self.DH-self.DS)-self.DP+90.+2.*self.DXI-self.DNU
    elif constituent == "Q1":
      return self.DT-3.*self.DS+self.DH+self.DP+90.+2.*self.DXI-self.DNU
    elif constituent == "T2":
      return 2.*self.DT-self.DH+self.DP1
    elif constituent == "R2":
      return 2.*self.DT+self.DH-self.DP1+180.
    elif constituent == "2Q1":
      return self.DT-4.*self.DS+self.DH+2.*self.DP+90.+2.*self.DXI-self.DNU
    elif constituent == "P1":
      return self.DT-self.DH+90.
    elif constituent == "2SM2":
      return 2.*(self.DT+self.DS-self.DH)+2.*(self.DNU-self.DXI)
    elif constituent == "M3":
      return 3.*(self.DT-self.DS+self.DH)+3.*(self.DXI-self.DNU)
    elif constituent == "L2":
      return 2.*(self.DT+self.DH)-self.DS-self.DP+180.+2.*(self.DXI-self.DNU)-self.DR
    elif constituent == "2MK3":
      return  3.*(self.DT+self.DH)-4.*self.DS+90.+4.*(self.DXI-self.DNU)+self.DNUP
    elif constituent == "K2":
      return 2.*(self.DT+self.DH)-2.*self.DNUP2
    elif constituent == "M8":
      return 8.*(self.DT-self.DS+self.DH)+8.*(self.DXI-self.DNU)
    elif constituent == "MS4":
      return 2.*(2.*self.DT-self.DS+self.DH)+2.*(self.DXI-self.DNU)

  def _EQ73(self):
    """ """
    return (2./3.-np.sin(self.I)**2)/.5021

  def _EQ74(self):
    """ """
    return np.sin(self.I)**2/.1578

  def _EQ75(self):
    """ """
    return np.sin(self.I)*np.cos(self.I/2.)**2/.37988

  def _EQ76(self):
    """ """
    return np.sin(2.*self.I)/.7214

  def _EQ77(self):
    """ """
    return np.sin(self.I)*np.sin(self.I/2.)**2/.0164

  def _EQ78(self):
    """ """
    return (np.cos(self.I/2)**4)/.91544

  def _EQ149(self):
    """ """
    return np.cos(self.I/2.)**6/.8758

  def _EQ197(self):
    """ """
    return np.sqrt(2.310+1.435*np.cos(2.*(self.P - self.XI)))

  def _EQ207(self):
    """ """
    return self._EQ75()*self._EQ197()

  def _EQ213(self):
    """ """
    return np.sqrt(1.-12.*np.tan(self.I/2.)**2*np.cos(2.*self.P)+36.*np.tan(self.I/2.)**4)
    
  def _EQ215(self):
    """ """
    return self._EQ78()*self._EQ213()

  def _EQ227(self):
    """ """
    return np.sqrt(.8965*np.sin(2.*self.I)**2+.6001*np.sin(2.*self.I)*np.cos(self.NU)+.1006)

  def _EQ235(self):
    """ """
    return .001+np.sqrt(19.0444*np.sin(self.I)**4+2.7702*np.sin(self.I)**2*np.cos(2.*self.NU)+.0981)