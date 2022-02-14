# Copyright (c) 2022, Vienna University of Technology (TU Wien), Department
# of Geodesy and Geoinformation (GEO).
# All rights reserved.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL VIENNA UNIVERSITY OF TECHNOLOGY,
# DEPARTMENT OF GEODESY AND GEOINFORMATION BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


import math
from osgeo import ogr
import numpy as np
import pandas as pd
from raster_binary_validation.input import read_file, rasterize
from raster_binary_validation.output import save_file


def run(ras_data_filepath, v_val_data_filepath, diff_ras_out_filepath='val.tif',
        v_reprojected_filepath='reproj_tmp.shp', v_rasterized_filepath='rasterized_val.tif',
        out_csv_filepath='val.csv', ex_filepath=None):
    """
    Runs the validation with vector data input (presence = 1, absence=0).

    Parameters
    ----------
    ras_data_filepath
    v_val_data_filepath
    diff_ras_out_filepath
    v_reprojected_filepath
    v_rasterized_filepath
    out_csv_filepath
    ex_filepath
    """

    vec_ds = ogr.Open(v_val_data_filepath)
    flood_data, gt, sref = read_file(ras_data_filepath)

    if ex_filepath is None:
        ex_data = None
    else:
        ex_data = read_file(ex_filepath)[0]

    print('rasterizing')
    val_data = rasterize(vec_ds, v_rasterized_filepath, flood_data, gt, sref,
                         v_reprojected_filepath=v_reprojected_filepath)
    print('done ... rasterizing')

    print('start validation')
    res, idx, UA, PA, Ce, Oe, CSI, F1, SR, K, A = validate(flood_data, val_data, mask=ex_data, data_nodata=255,
                                                           val_nodata=255)

    # save results
    res = res.astype(np.uint8)
    res[~idx] = 255
    save_file(diff_ras_out_filepath, res, nodata=255, gt=gt, sref=sref)

    #
    dat = [['result 1', UA, PA, Ce, Oe, CSI, F1, SR, K, A]]
    df = pd.DataFrame(dat,
                      columns=['file', "User's Accuracy/Precision", "Producer's Accuracy/Recall", 'Commission Error',
                               'Omission Error', 'Critical Success Index', 'F1', 'Success Rate', 'Kappa', 'Accuracy'])
    df.to_csv(out_csv_filepath)
    print('end validation')


def validate(data, val_data, mask=None, data_nodata=255, val_nodata=255):
    """
    Runs validation on aligned numpy arrays.

    Parameters
    ----------
    data: numpy.array
        Binary classification result which will be validated.
    val_data: numpy.array
        Binary reference data array.
    mask: numpy.array
        Binary mask to be applied on both input arrays.
    data_nodata: int, optional
        No data value of the classification result (default: 255).
    val_nodata: int, optional
        No data value of the reference data (default: 255).

    Returns
    -------
    res: numpy.array
        Array which includes the differences of reference data and binary result.
    valid: numpy.array
        Array which includes the pixels which have valid data
    UA: float
        User's accuracy/Precision
    PA: float
        Producer's accuracy/Recall
    Ce: float
        Comission error
    Oe: float
        Omission error
    CSI: float
        Critical success index
    F1: float
        F1-score
    SR: float
        Success rate
    K: float
        Kappa coefficient
    A: float
        Accuracy
    """

    res = 1 + (2 * data) - val_data
    res[data == data_nodata] = 255
    res[val_data == val_nodata] = 255

    if mask is not None:
        res[mask == 1] = 255
        data[mask == 1] = 255  # applying exclusion, setting exclusion pixels as no data
    valid = np.logical_and(val_data != 255, data != 255)  # index removing no data from comparison

    TP = np.sum(res == 2)
    TN = np.sum(res == 1)
    FN = np.sum(res == 0)
    FP = np.sum(res == 3)
    print(np.array([[TP, FP], [FN, TN]]))

    # calculating metrics
    Po = A = (TP + TN) / (TP + TN + FP + FN)
    Pe = ((TP + FN) * (TP + FP) + (FP + TN) * (FN + TN)) / (TP + TN + FP + FN) ** 2
    K = (Po - Pe) / (1 - Pe)
    UA = TP / (TP + FP)
    PA = TP / (TP + FN)  # accuracy:PP2 as defined in ACube4Floods 5.1
    CSI = TP / (TP + FP + FN)
    F1 = (2 * TP) / (2 * TP + FN + FP)
    Ce = FP / (FP + TP)  # inverse of precision
    Oe = FN / (FN + TP)  # inverse of recall
    P = math.exp(FP / ((TP + FN) / math.log(0.5)))  # penalization as defined in ACube4Floods 5.1
    SR = PA - (1 - P)  # Success rate as defined in ACube4Floods 5.1

    print("User's Accuracy/Precision: %f" % (UA))
    print("Producer's Accuracy/Recall/PP2: %f" % (PA))
    print("Critical Success In: %f" % (CSI))
    print("F1: %f" % (F1))
    print("commission error: %f" % (Ce))
    print("omission error: %f" % (Oe))
    print("total accuracy: %f" % (A))
    print("kappa: %f" % (K))
    print("Penalization Function: %f" % (P))
    print("Success Rate: %f" % (SR))

    return res, valid, UA, PA, Ce, Oe, CSI, F1, SR, K, A


def validate_raster(in_filepath, val_filepath, results_filepath, exclusion_filepath=None):
    """
    Validates raster reference file with raster map. Assumes files are aligned, same projection and extent.

    Parameters
    ----------
    in_filepath: str
        Path of the input classification result.
    val_filepath: str
        Path of the reference data.
    results_filepath: str
        Path of the output omission/comission map.
    exclusion_filepath: str, optional
        Path of the exclusion layer to be applied on the other input layers.

    Returns
    -------
    file_name: str
        Name of the output map.
    Several validation measures: float
        Measures to describe the validation result (UA, PA, Ce, Oe, CSI, F1, SR, K, A).
    """
    # TODO: combine vector and raster validation functions and solve open issues
    data, gt, sref = read_file(in_filepath)
    val_data, gt_val, sref_val = read_file(val_filepath)

    if exclusion_filepath is None:
        exclusion_data = None
    else:
        exclusion_data = read_file(exclusion_filepath)[0]
        # need to add projection check, assume same as validation data

    res, idx, UA, PA, Ce, Oe, CSI, F1, SR, K, A = validate(data, val_data, mask=exclusion_data, data_nodata=255,
                                                           val_nodata=255)

    save_file(results_filepath, res, nodata=255, gt=gt, sref=sref)

    return file_name, UA, PA, Ce, Oe, CSI, F1, SR, K, A
