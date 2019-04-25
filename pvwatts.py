"""
PVWatts Emulator
"""
import pvlib
from psm3 import get_psm3
import json
import requests
from bokeh.plotting import figure
from bokeh.embed import components
from flask import (
    Flask, request, render_template, abort, Response, redirect, url_for, flash
)

app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
@app.route('/<header>', methods=['GET', 'POST'])
def pvwatts(latitude=None, longitude=None, trackerCheck=None, azimuth=None,
            tilt=None, moduleTypeRadios=None, projectSize=None, dstCheck=None,
            output=None, header=None):
    if request.method == 'GET':
        kwargs = {'title': 'PVWatts'}
        if output is not None:
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                pass
            else:
                plot = figure(title='squares from input')
                # plot.line(xdata, [x*x for x in xdata], legend='y=x^2')
                plot_script, plot_div = components(plot)
                kwargs.update(plot_script=plot_script, plot_div=plot_div)
        return render_template('pvwatts.html', **kwargs)
    elif request.method == 'POST':
        latitude = request.form.get('latitude', 40.5137)
        latitude = float(latitude)
        longitude = request.form.get('longitude', -108.5449)
        longitude = float(longitude)
        try:
            header, data = get_psm3(latitude, longitude)
        except requests.HTTPError as exc:
            flash(exc, 'error')
            return render_template('pvwatts.html', title='PVWatts')
        else:
            return render_template('pvwatts.html', header=header)
        #redirect(url_for('pvwatts', header=header))

    abort(404)
    abort(Response('PVWatts'))


if __name__ == '__main__':
    app.run(debug=True)
