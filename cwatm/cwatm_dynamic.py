# -------------------------------------------------------------------------
# Name:       CWAT Model Dynamic
# Purpose:
#
# Author:      burekpe
#
# Created:     16/05/2016
# Copyright:   (c) burekpe 2016
# -------------------------------------------------------------------------

from cwatm.management_modules.data_handling import *
from cwatm.management_modules.messages import *


import time
import pandas as pd

class CWATModel_dyn(DynamicModel):

    # =========== DYNAMIC ====================================================

    def dynamic(self):
        """
        Dynamic part of CWATM
        calls the dynamic part of the hydrological modules
        Looping through time and space

        Note:
            if flags set the output on the screen can be changed e.g.

            * v: no output at all
            * l: time and first gauge discharge
            * t: timing of different processes at the end
        """

        # self.CalendarDate = dateVar['dateStart'] + datetime.timedelta(days=dateVar['curr'])
        # self.CalendarDay = int(self.CalendarDate.strftime("%j"))
        timestep_dynamic(self)

        del timeMes[:]
        timemeasure("Start dynamic")

        # ************************************************************
        """ up to here it was fun, now the real stuff starts
        """

        if checkOption('calc_environflow') and (returnBool('calc_ef_afterRun') == False):
            # if only the dis is used for calculation of EF
            self.environflow_module.dynamic()
            self.output_module.dynamic(ef=True)
            header = "\n\n ======================== CWATM ONLY EF calculation===========\n"
            print(header + "done with Environmental Flow\n")
            sys.exit(400)

        self.readmeteo_module.dynamic()
        timemeasure("Read meteo")  # 1. timing after read input maps

        if Flags['calib']:
            self.output_module.dynamic()
            return

        self.evaporationPot_module.dynamic()
        timemeasure("ET pot")  # 2. timing after read input maps

        # if Flags['check']: return  # if check than finish here

        """ Here it starts with hydrological modules:
        """

        # ***** INFLOW HYDROGRAPHS (OPTIONAL)****************
        self.inflow_module.dynamic()
        self.lakes_reservoirs_module.dynamic()

        # ***** RAIN AND SNOW *****************************************
        self.snowfrost_module.dynamic()
        timemeasure("Snow")  # 3. timing

        # ***** READ land use fraction maps***************************
        if dateVar['newYear']  and not dateVar['newStart']:
            # save last year landcover fraction to guess transition in the water quality module
            self.var.fracVegCover_former = self.var.fracVegCover.copy()
            
        self.landcoverType_module.dynamic_fracIrrigation(init=dateVar['newYear'], dynamic=self.var.dynamicLandcover)
        self.capillarRise_module.dynamic()
        timemeasure("Soil 1.Part")  # 4. timing

        # *********  Soil splitted in different land cover fractions *************
        self.landcoverType_module.dynamic()
        timemeasure("Soil main")  # 5. timing
         
        if self.var.modflow:
            self.groundwater_modflow_module.dynamic()
        else:
            self.groundwater_module.dynamic()
        timemeasure("Groundwater")  # 7. timing

        self.runoff_concentration_module.dynamic()
        timemeasure("Runoff conc.")  # 8. timing
        
        if self.var.includeWaterQuality:
            self.waterquality_module.dynamic()
            timemeasure("Water_Quality")
        self.lakes_res_small_module.dynamic()
        timemeasure("Small lakes")  # 9. timing
        
        self.routing_kinematic_module.dynamic()

        timemeasure("Routing_Kin")  # 10. timing


        # calculate Total water storage (tws) [m] as a sum of
        # Groundwater [m] + soil [m] + lake and reservoir storage [m3] + channel storage [m3]
        # [m3] >> [m] --> * InvCellArea

        if self.var.modflow:
            groundwater_storage = self.var.groundwater_storage_available
        else:
            groundwater_storage = self.var.storGroundwater

        if (checkOption('includeRouting')):
            self.var.totalET_WB = self.var.EvapoChannel
            if checkOption('includeWaterBodies'):
                if returnBool('useSmallLakes'):
                    # Sum off lake and reservoirs and small lakes
                    self.var.lakeReservoirStorage = self.var.lakeResStorage + self.var.smalllakeStorage
                else:
                    # Sum off lake and reservoirs - here without small lakes
                    self.var.lakeReservoirStorage = self.var.lakeResStorage

                self.var.tws = groundwater_storage + self.var.totalSto \
                               + self.var.lakeReservoirStorage * self.var.InvCellArea \
                               + self.var.channelStorage * self.var.InvCellArea

                self.var.totalET_WB = self.var.totalET_WB + self.var.totalET + self.var.EvapWaterBodyM
                if returnBool('useSmallLakes'):
                    self.var.totalET_WB = self.var.totalET_WB + self.var.smallevapWaterBody
            else:
                self.var.tws = groundwater_storage + self.var.totalSto + self.var.channelStorage * self.var.InvCellArea
        else:
            self.var.tws = groundwater_storage + self.var.totalSto

        if checkOption('includeRunoffConcentration'):
            self.var.tws = self.var.tws + self.var.gridcell_storage
        
        if self.var.includeWaterQuality:
            if self.var.includePhosphorus:
                self.var.channel_TP = self.var.channel_P + self.var.channel_PP + self.var.channel_inactiveP
                self.var.resLake_TP = self.var.resLake_P + self.var.resLake_PP + self.var.resLake_inactiveP
                self.var.channel_TPConc = np.where(self.var.channelStorage > 1, divideValues(self.var.channel_TP, self.var.channelStorage), 0.) * 10**3
                self.var.channel_TDPConc = np.where(self.var.channelStorage > 1, divideValues(self.var.channel_P, self.var.channelStorage), 0.) * 10**3
                self.var.resLake_TPConc = divideValues(self.var.resLake_TP, self.var.lakeResStorage) * 10**3
                self.var.resLake_TDPConc = divideValues(self.var.resLake_P, self.var.lakeResStorage) * 10**3
        # *******  Calculate CUMULATIVE MASS BALANCE ERROR  **********
        # self.waterbalance_module.dynamic()

        # ------------------------------------------------------
        # End of calculation -----------------------------------
        # ------------------------------------------------------

        self.waterbalance_module.checkWaterSoilGround()
        timemeasure("Waterbalance")  # 11. timing

        self.environflow_module.dynamic()
        # in case environmental flow is calculated last

        self.output_module.dynamic()
        timemeasure("Output")  # 12. timing
        
        self.init_module.dynamic()
        if self.currentStep == self.firstStep:
            self.timeMesTbl = pd.DataFrame(np.array([np.array(timeMes)]), index = [self.currentStep])
        else:
            self.timeMesTbl = pd.concat([self.timeMesTbl, pd.DataFrame(np.array([np.array(timeMes)]), index = [self.currentStep])])
       
        for i in range(len(timeMes)):
            
            # if self.currentTimeStep() == self.firstTimeStep():
            if self.currentStep == self.firstStep:
                timeMesSum.append(timeMes[i] - timeMes[0])                
            else:
                timeMesSum[i] += timeMes[i] - timeMes[0]
        # if modflow is used, the temporary files produced by Modflow/Flopy have to be closed with finalize
        # otherwise they cannot be opend in the next run by pytest or calibration
        if self.var.modflow:
            if self.currentStep == self.lastStep:
                self.groundwater_modflow_module.modflow.finalize()
                
        '''
        if self.currentStep == self.lastStep:
            if self.var.includeWaterQuality:
                colNms = {'0':'Start_dynamic', '1':'read_meteo',\
                    '2':'et_pot', '3':'snow', '4':'Soil_1part',	'5':'Soil_main',\
                    '6':'groundwater', '7':'runoff_conc', '8':'Water_Quality',\
                    '9':'small_lakes', '10':'RoutingKin', '11':'Waterbalance',\
                    '12':'Output'}
                colNms = ['Start_dynamic', 'read_meteo', 'et_pot', 'snow',\
                    'Soil_1part', 'Soil_main', 'groundwater', 'runoff_conc', 
                    'Water_Quality', 'small_lakes', 'RoutingKin', 'Waterbalance',\
                    'Output']
                pth_out = "c:/users/dof19/dropbox/iiasa/cwatm_wq_dev/elvba/timing_with_wq.csv"
            else:
                colNms = ['Start_dynamic', 'read_meteo', 'et_pot', 'snow',\
                    'Soil_1part', 'Soil_main', 'groundwater', 'runoff_conc', 
                    'small_lakes', 'RoutingKin', 'Waterbalance',\
                    'Output']
                pth_out = "c:/users/dof19/dropbox/iiasa/cwatm_wq_dev/elvba/timing_without_wq.csv"


            self.timeMesTbl.columns = colNms

            self.timeMesTbl.to_csv(pth_out)
        '''
        #self.var.sumsum_directRunoff += self.var.sum_directRunoff
        #self.var.sumsum_Runoff += self.var.sum_directRunoff
        #self.var.sumsum_Precipitation += self.var.Precipitation
        #self.var.sumsum_gwRecharge += self.var.sum_gwRecharge
        #runoff = self.var.baseflow + self.var.sum_landSurfaceRunoff
        #self.var.sumsum_Runoff += runoff

        #print self.sum_directRunoff,  self.sum_interflowTotal, self.sum_landSurfaceRunoff, self.baseflow, runoff
        #print self.sumsum_Precipitation, self.sumsum_Runoff

        #report(decompress(self.var.sum_potTranspiration), "c:\work\output/trans.map")
        #report(decompress(self.var.directRunoff[3 ]), "c:\work\output\dir.map")
        #report(decompress(runoff), "c:\work\output\dirsum.map")
        #report(decompress(self.sumsum_Precipitation), "c:\work\output\prsum.map")
        #report(decompress(runoff), "c:\work\output/runoff.map")
