#!/usr/bin/env python3

# Author: Heresh Fattahi

import os
import glob
import argparse
import numpy as np
from osgeo import gdal
import isce
import isceobj
from scipy.interpolate import griddata
import shelve
import datetime
import time
from Network import Network
from SARTS import util

def cmdLineParser(iargs = None):
    '''
    Command line parser.
    '''

    parser = argparse.ArgumentParser(description = 'integrate PS pixels into existing unwrapped DS filed',
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-s', '--slc_stack', type=str, dest='slcStack',
            required=True, help='slc stack dataset ')

    parser.add_argument('-d', '--ds_stack_dir', type=str, dest='dsStackDir',
            required=True, help='The directory that contains adjusted stack based on DS analysis')

    parser.add_argument('-t', '--tcorr_file', type=str, dest='tcorrFile',
            required=True, help='A temporal coheremce file which represents the coherence of the stack')

    parser.add_argument('-p', '--psPixels_file', type=str, dest='psPixelsFile',
            required=True, help='The map of PS pixles')

    parser.add_argument('-o', '--output_dir', type=str, dest='outDir',
            required=True, help='The output directory to store the wrapped phase series of DS and PS pixels')

    parser.add_argument('-c', '--coreg_slc_dir', type=str, dest='coregSlcDir',
            required=False, help='The directory that contains the coregistered stack of SLCs')

    parser.add_argument('-u', '--unw_method', '--unwrap_method', type=str, dest='unwrapMethod', choices=('snaphu','phass'),
            help='phase unwrapping method. e.g., snaphu, phass. If enabled, a shell file "run_unwrap_ps_ds.sh" with unwrap command will be created.')

    parser.add_argument('-x', '--xml_file', type=str, dest='xmlFile',
            required=False, help='path of reference xml file for unwrapping with snaphu')

    return parser.parse_args()

def rewrap(data):
    return data - np.round(data/2.0/np.pi)*2.0*np.pi


def get_DS_unwrapped_phase(ds, bandi, bandj , x0, y0, xoff, yoff):

    if bandi>1:
        unwi = ds.GetRasterBand(bandi).ReadAsArray(x0, y0, xoff, yoff)
        unwj = ds.GetRasterBand(bandj).ReadAsArray(x0, y0, xoff, yoff)
        unw = unwj-unwi
    else:
        unw = ds.GetRasterBand(bandj).ReadAsArray(x0, y0, xoff, yoff)

    return unw

def get_fullres_ifgram(ds, bandi, bandj, x0, y0, xoff, yoff):

    # crossmultiply two SLCs
    # TODO: need to use actual crossmul module to avoid aliasing
    slci = ds.GetRasterBand(bandi).ReadAsArray(x0, y0, xoff, yoff)
    slcj = ds.GetRasterBand(bandj).ReadAsArray(x0, y0, xoff, yoff)
    ifgram = np.exp(1J*np.angle(slci*np.conjugate(slcj)))

    return ifgram

def writeToFile(data , ds , xoff, yoff):

    ds.GetRasterBand(1).WriteArray(data, xoff, yoff)


    format = "ENVI"
    driver = gdal.GetDriverByName(format)

    [cols, rows] = ampDisp.shape

    outDataRaster = driver.Create("k_means.bin", rows, cols, 1, gdal.GDT_Byte)
    outDataRaster.SetGeoTransform(ds.GetGeoTransform())##sets same geotransform as input
    outDataRaster.SetProjection(ds.GetProjection())##sets same projection as input

    outDataRaster.GetRasterBand(1).WriteArray(X_cluster)
    outDataRaster.FlushCache() ## remove from memory

def integratePS2DS(dsDS_band_i, dsDS_band_j, dsSlc, dsTcor, psDataset, outDataset,
                       nblocks, linesPerBlock, band_i, band_j):

    nrows = dsDS_band_i.RasterYSize
    ncols = dsDS_band_i.RasterXSize

    x0 = 0
    xoff = ncols

    for block in range(nblocks):

        print("block: ", block)

        y0 = block*linesPerBlock

        if (y0 + linesPerBlock) > nrows:
            yoff = nrows - y0
        else:
            yoff = linesPerBlock

        tcorr = dsTcor.ReadAsArray(x0, y0, xoff, yoff)

        psPixels = psDataset.ReadAsArray(x0, y0, xoff, yoff)

        band_i_DS = dsDS_band_i.ReadAsArray(x0, y0, xoff, yoff)
        band_j_DS = dsDS_band_j.ReadAsArray(x0, y0, xoff, yoff)

        ifgram = get_fullres_ifgram(dsSlc, band_i, band_j, x0, y0, xoff, yoff)

        # pair i-j of DS pixels
        ifgram_ds_ps = band_i_DS * np.conjugate(band_j_DS)

        # get the data for PS pixels
        ifgram_ds_ps[psPixels == 1] = ifgram[psPixels == 1]

        print(ifgram.dtype)
        outDataset.GetRasterBand(1).WriteArray(ifgram_ds_ps, x0, y0)

    return None


def getCoherence(dsTcor, psDataset, outDataset,
      ncols, nrows, nblocks, linesPerBlock):

    x0 = 0
    xoff = ncols

    for block in range(nblocks):

        print("block: ", block)

        y0 = block*linesPerBlock

        if (y0 + linesPerBlock) > nrows:
            yoff = nrows - y0
        else:
            yoff = linesPerBlock

        tcorr = dsTcor.ReadAsArray(x0, y0, xoff, yoff)

        psPixels = psDataset.ReadAsArray(x0, y0, xoff, yoff)

        tcorr[psPixels==1] = 0.95

        outDataset.GetRasterBand(1).WriteArray(tcorr, x0, y0)

    return None


def main(inps):

    # inps = cmdLineParser(iargs)

    # Open the SLC dataset to read
    dsSlc = gdal.Open(inps.slcStack, gdal.GA_ReadOnly)

    # Open the tcorr dataset
    dsTcor = gdal.Open(inps.tcorrFile, gdal.GA_ReadOnly)

    # Open the PS pixels dataset
    psDataset = gdal.Open(inps.psPixelsFile, gdal.GA_ReadOnly)

    nSlc = dsSlc.RasterCount
    nrows = dsSlc.RasterYSize
    ncols = dsSlc.RasterXSize

    print("number of SLC: ", nSlc)
    print("number of rows: ", nrows)
    print("number of columns: ", ncols)

    linesPerBlock = 8000
    nblocks = int(nrows/linesPerBlock)
    if (nblocks == 0):
        nblocks = 1
    elif (nrows % (nblocks * linesPerBlock) != 0):
        nblocks += 1

    print("nblocks: ", nblocks)

    if not os.path.exists(inps.outDir):
        os.makedirs(inps.outDir)

    driver = gdal.GetDriverByName("ENVI")
    corName = os.path.join(inps.outDir, "tcorr_ds_ps.bin")
    corDataset = driver.Create(corName, ncols, nrows, 1, gdal.GDT_Float32)
    getCoherence(dsTcor, psDataset, corDataset,
                 ncols, nrows, nblocks, linesPerBlock)
    corDataset.FlushCache()

    # extract the list of the dates
    dateList = []
    for band in range(nSlc):
        date_i =dsSlc.GetRasterBand(band + 1).GetMetadata("slc")["Date"]
        dateList.append(date_i)
    dateList.sort()

    # # setup a network, compute coherence based on geometry, find min span tree pairs
    # networkObj = Network()
    # networkObj.dates = inps.dates

    # loop over all pairs
    for pair in inps.pairs:
        date_i = pair.split('_')[0]
        date_j = pair.split('_')[1]
        outName = os.path.join(inps.outDir,pair, "{0}_{1}.int".format(date_i, date_j))
        lkFile = os.path.join(inps.outDir,pair, 'fine_lk.int')

        # we won't make the ifg if there is already an ifg OR a downlooked ifg.
        if not os.path.isfile(outName) and not os.path.isfile(lkFile):
            
            print('Making ' + outName)

            band_i = dateList.index(date_i) + 1
            band_j = dateList.index(date_j) + 1

            outDir = os.path.join(inps.outDir,pair)
            if not os.path.isdir(outDir):
                os.system('mkdir -p ' + outDir)

            # name of the output file witth both PS and DS pixels

            # dataset for the PS-DS integrated wrapped phase
            driver = gdal.GetDriverByName("ENVI")
            outDataset = driver.Create(outName, ncols, nrows, 1, gdal.GDT_CFloat32)

            dsDS_band_i = gdal.Open(os.path.join(inps.dsStackDir, date_i + ".slc.vrt"), gdal.GA_ReadOnly)
            dsDS_band_j = gdal.Open(os.path.join(inps.dsStackDir, date_j + ".slc.vrt"), gdal.GA_ReadOnly)

            # integrate PS to DS for this pair and write to file block by block
            integratePS2DS(dsDS_band_i, dsDS_band_j, dsSlc, dsTcor, psDataset, outDataset,
                           nblocks, linesPerBlock, band_i, band_j)

            # close the dataset
            outDataset.FlushCache()
            dsDS_band_i = None
            dsDS_band_j = None

            util.write_xml(outName,ncols,nrows,1,dataType='CFLOAT',scheme='BIP')
        else:
            print(outName + ' already exists')
            
    # write the unwrapping command for this pair
    if inps.unwrapMethod is not None:
        # prepare output dir
        unwDir = os.path.join(inps.outDir, "unwrap")
        if not os.path.exists(unwDir):
            os.makedirs(unwDir)

        # an output script with commands to unwrap interferograms
        run_outname = "run_unwrap_ps_ds.sh"
        runf= open(run_outname,'w')
        runf.write("set -e\n")

        for pair in inps.pairs:
            date_i = pair.split('-')[0]
            date_j = pair.split('-')[1]
            intName = os.path.join(inps.outDir, "{0}_{1}.int".format(date_i, date_j))
            unwName = os.path.join(unwDir, "{0}_{1}.unw".format(date_i, date_j))
            if inps.xmlFile is None:
                cmd = "unwrap_fringe.py -m " + inps.unwrapMethod + " -i " + intName + " -c " + corName + " -o " + unwName
                runf.write(cmd + "\n")
            else:
                cmd = "unwrap_fringe.py -m " + inps.unwrapMethod + " -i " + intName + " -c " + corName + " -o " + unwName + " -x " + inps.xmlFile
                runf.write(cmd + "\n")
        runf.close()

    dsSLC = None
    dsUnw = None
    dsTcor = None
    psDataset = None

# if __name__ == '__main__':
#     '''
#     Main driver.
#     '''
#     main()
