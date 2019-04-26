"""
PVWatts Emulator
"""
import json
import pvlib
import threading
import queue
from psm3 import get_psm3
import pandas as pd
import requests
from bokeh.plotting import figure
from bokeh.embed import components
from flask import (
    Flask, request, render_template, abort, Response, redirect, url_for, flash
)

YEAR = 1990
STARTDATE = '%d-01-01T00:00:00' % YEAR
ENDDATE = '%d-12-31T23:59:59' % YEAR
TIMES = pd.DatetimeIndex(start=STARTDATE, end=ENDDATE, freq='H')
INVERTERS = pvlib.pvsystem.retrieve_sam('CECInverter')
INVERTER_10K = INVERTERS['SMA_America__SB10000TL_US__240V__240V__CEC_2018_']
CECMODS = pvlib.pvsystem.retrieve_sam('CECMod')
CECMOD_POLY = CECMODS['Canadian_Solar_CS6X_300P']
CECMOD_MONO = CECMODS['Canadian_Solar_CS6X_300M']

app = Flask(__name__)

ROUTE = (
    '/<latitude>/<longitude>/<tracker>/<surface_azimuth>/<surface_tilt>'
    '/<module_type>/<project_size>/<dst>')
LATITUDE, LONGITUDE = 40.5137, -108.5449

@app.route('/', methods=['GET', 'POST'])
@app.route(ROUTE, methods=['GET', 'POST'])
def pvwatts(latitude=LATITUDE, longitude=LONGITUDE, tracker=False,
            surface_azimuth=0.0, surface_tilt=20.0, module_type=None,
            project_size=None, dst=False):
    kwargs = {'title': 'PVWatts'}
    if request.method == 'GET':
        mpp, header = calculate(
            latitude, longitude, tracker, surface_tilt, surface_azimuth)
        kwargs['header'] = header
        mpp = pd.DataFrame(mpp, index=TIMES)
        Edaily = mpp.p_mp.resample('D').sum()
        plot = figure(title='Daily Energy', x_axis_type="datetime")
        plot.line(Edaily.index, Edaily, legend='energy')
        plot_script, plot_div = components(plot)
        kwargs.update(plot_script=plot_script, plot_div=plot_div)
        return render_template('pvwatts.html', **kwargs)
    elif request.method == 'POST':
        # get solar resourece from PSM3
        latitude = request.form.get('latitude', 40.5137)
        latitude = float(latitude)  # html already validates number type
        longitude = request.form.get('longitude', -108.5449)
        longitude = float(longitude)  # html already validates number type
        tracker = request.form.get('trackerCheck', False)
        surface_azimuth, surface_tilt = 0., 0.
        if not tracker:
            surface_azimuth = request.form.get('azimuth', 0.)
            surface_azimuth = float(surface_azimuth)  # already number type
            surface_tilt = request.form.get('tilt', 20.)
            surface_tilt = float(surface_tilt)  # already validated by html
        kwargs = {
            'latitude': latitude, 'longitude': longitude, 'tracker': tracker,
            'surface_tilt': surface_tilt, 'surface_azimuth': surface_azimuth}
        return redirect(url_for('pvwatts', **kwargs))

    abort(404)
    abort(Response('PVWatts'))


def calculate(latitude, longitude, tracker, surface_tilt, surface_azimuth):
    # TODO: put in a thread
    try:
        header, data = get_psm3(latitude, longitude)
    except requests.HTTPError as exc:
        flash(exc, 'error')
        return render_template('pvwatts.html', title='PVWatts')
    # get solar position
    times = data.index
    sp = pvlib.solarposition.get_solarposition(
        times, latitude, longitude)
    solar_zenith = sp.apparent_zenith.values
    solar_azimuth = sp.azimuth.values
    dni = data.DNI.values
    ghi = data.GHI.values
    dhi = data.DHI.values
    surface_albedo = data['Surface Albedo'].values
    temp_air = data.Temperature.values
    # airmass_relative = pvlib.atmosphere.get_relative_airmass(
    #     solar_zenith)
    # airmass_absolute = pvlib.atmosphere.get_absolute_airmass(
    #     airmass_relative)
    dni_extra = pvlib.irradiance.get_extra_radiation(times).values
    if tracker:
        tracker = pvlib.tracking.singleaxis(solar_zenith, solar_azimuth)
        surface_tilt = tracker.surface_tilt.values
        surface_azimuth = tracker.surface_azimuth.values
    poa_sky_diffuse = pvlib.irradiance.get_sky_diffuse(
        surface_tilt, surface_azimuth, solar_zenith, solar_azimuth,
        dni, ghi, dhi, dni_extra=dni_extra, model='haydavies')
    if not tracker:
        aoi = pvlib.irradiance.aoi(
            surface_tilt, surface_azimuth, solar_zenith, solar_azimuth)
    else:
        aoi = tracker.aoi.values
    poa_ground_diffuse = pvlib.irradiance.get_ground_diffuse(
        surface_tilt, ghi, albedo=surface_albedo)
    poa = pvlib.irradiance.poa_components(
        aoi, dni, poa_sky_diffuse, poa_ground_diffuse)
    poa_direct = poa['poa_direct']
    poa_diffuse = poa['poa_diffuse']
    poa_global = poa['poa_global']
    iam = pvlib.pvsystem.ashraeiam(aoi)
    effective_irradiance = poa_direct*iam + poa_diffuse
    temp_cell = pvlib.pvsystem.pvsyst_celltemp(poa_global, temp_air)
    cecparams = pvlib.pvsystem.calcparams_cec(
        effective_irradiance, temp_cell,
        CECMOD_MONO.alpha_sc, CECMOD_MONO.a_ref,
        CECMOD_MONO.I_L_ref, CECMOD_MONO.I_o_ref,
        CECMOD_MONO.R_sh_ref, CECMOD_MONO.R_s, CECMOD_MONO.Adjust)
    mpp = pvlib.pvsystem.max_power_point(*cecparams, method='newton')
    return mpp, header


if __name__ == '__main__':
    app.run(debug=True)
