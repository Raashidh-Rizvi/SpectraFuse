import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, CalendarDays, Download, Flame, Layers, MapPin, Orbit} from 'lucide-react';
import {Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';

const base = '/api/fire';
const modis = 'MODIS_SP', viirs = 'VIIRS_SNPP_SP', noaa = 'VIIRS_NOAA20_SP';
const names = {[modis]:'MODIS', [viirs]:'VIIRS S-NPP', [noaa]:'VIIRS NOAA-20', harmonized:'VIIRS-scale'};
const months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ');
const format = n => n == null ? '—' : new Intl.NumberFormat('en', {maximumFractionDigits:1}).format(n);

async function get(path, signal) {
  const response = await fetch(base + path, {signal});
  if (!response.ok) throw new Error('Data could not be loaded. Check that FastAPI is running.');
  return response.json();
}

function DetectionMap({cells, loading}) {
  const element = useRef(null);
  const map = useRef(null);
  useEffect(() => {
    const view = L.map(element.current, {scrollWheelZoom:false}).setView([7.8,80.7],7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(view);
    map.current = view;
    const observer = new ResizeObserver(() => view.invalidateSize());
    observer.observe(element.current);
    return () => {observer.disconnect(); view.remove();};
  }, []);
  useEffect(() => {
    const group = L.layerGroup(cells.map(cell => L.circleMarker([cell.latitude,cell.longitude], {
      color:'#d9faff', fillColor:'#5868f4', fillOpacity:.8, weight:1, radius:Math.min(23,4+Math.sqrt(cell.count))
    }).bindTooltip(format(cell.count) + ' detections'))).addTo(map.current);
    return () => group.remove();
  }, [cells]);
  return <div className="mapwrap"><div ref={element} className="map" aria-label="Map of recorded fire detections"/>
    {loading && <span className="mapstatus">Loading detections…</span>}</div>;
}

function App() {
  const [rows,setRows] = useState([]), [metrics,setMetrics] = useState([]);
  const [year,setYear] = useState('all'), [measure,setMeasure] = useState('harmonized');
  const [selected,setSelected] = useState(''), [sensor,setSensor] = useState(viirs);
  const [map,setMap] = useState(null), [error,setError] = useState(''), [mapError,setMapError] = useState('');
  const [percent,setPercent] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([get('/dashboard',controller.signal),get('/sensor-comparison',controller.signal)])
      .then(([data,comparison]) => {
        setRows(data); setMetrics(comparison.metrics);
        setSelected(data.findLast(row => row[viirs] != null)?.month ?? '');
      }).catch(err => {if (!controller.signal.aborted) setError(err.message);});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setMap(null); setMapError('');
    get('/monthly-hotspots?month='+selected+'&source='+sensor,controller.signal).then(setMap)
      .catch(err => {if (!controller.signal.aborted) setMapError(err.message);});
    return () => controller.abort();
  }, [selected,sensor]);
  const years = [...new Set(rows.map(row => row.month.slice(0,4)))];
  const visible = rows.filter(row => year === 'all' || row.month.startsWith(year));
  const active = visible.filter(row => row[measure] != null);
  const selectedRow = rows.find(row => row.month === selected);
  const total = active.reduce((sum,row) => sum + row[measure],0);
  const peak = active.reduce((top,row) => !top || row[measure] > top[measure] ? row : top,null);
  const noaaMonths = rows.filter(row => row[noaa] != null).length;
  const anomalyKey = measure + '_anomaly';
  const maximum = Math.max(1,...visible.map(row => percent ? Math.abs(row[anomalyKey] ?? 0) : row[measure] ?? 0));
  const chart = visible.map(row => ({...row, activity:row[measure]}));
  const errorMetric = metrics.find(row => row.Method === 'Calibrated MODIS');
  return <main>
    <header><div className="brand"><div className="mark"><Flame size={23}/></div><div><strong>FireScope</strong><small>Satellite fire activity</small></div></div>
      <a className="button" href={base+'/download?region=sri-lanka'+(year==='all' ? '' : '&year='+year)}><Download size={16}/> Monthly CSV</a></header>
    <section className="intro"><div><p className="location"><MapPin size={15}/> Sri Lanka pilot</p><h1>Burning activity</h1><p>NASA FIRMS · Standard Processing · UTC</p></div>
      <div className="filters"><label><span>Sensor basis</span><select value={measure} onChange={e=>setMeasure(e.target.value)}>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
      <label><span>Year</span><select value={year} onChange={e=>{const value=e.target.value;setYear(value);if(value!=='all')setSelected(rows.findLast(r=>r.month.startsWith(value))?.month ?? '');}}><option value="all">All years</option>{years.map(value=><option key={value}>{value}</option>)}</select></label></div>
    </section>
    {error && <p role="alert" className="panel notice">{error}</p>}
    {!error && !rows.length && <p role="status" className="panel notice">Loading NASA FIRMS observations…</p>}
    {!!rows.length && <div className="dashboard">
      <section className="panel stat"><span><Layers size={17}/> Months with data</span><strong>{active.length}</strong><small>{visible[0]?.month} — {visible.at(-1)?.month}</small></section>
      <section className="panel stat"><span><Flame size={17}/> {names[measure]} detections</span><strong>{active.length ? format(total) : '—'}</strong><small>Sum across selected months</small></section>
      <section className="panel stat dark"><span><Activity size={17}/> Peak activity</span><strong>{peak?.month ?? '—'}</strong><small>{format(peak?.[measure])} detections</small></section>
      <section className="panel stat"><span><Orbit size={17}/> NOAA-20 coverage</span><strong>{noaaMonths}<em> / {rows.length}</em></strong><small>Complete months across the pilot</small></section>
      <section className="panel trend"><h2>Historical activity</h2><p>{names[measure]} monthly detections</p>
        <div className="chart"><ResponsiveContainer><AreaChart data={chart} margin={{left:1,right:13,top:10,bottom:0}}>
          <defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#8ef5ff" stopOpacity=".85"/><stop offset="100%" stopColor="#454cf9" stopOpacity=".16"/></linearGradient></defs>
          <CartesianGrid vertical={false} stroke="#c5d1ff35"/><XAxis dataKey="month" tick={{fill:'#dce6ff',fontSize:11}} minTickGap={28}/><YAxis width={49} tick={{fill:'#dce6ff',fontSize:11}}/>
          <Tooltip contentStyle={{background:'#1b2450',border:'1px solid #8ba0dd',borderRadius:10}} formatter={value=>[format(value),'Detections']}/>
          <Area type="monotone" dataKey="activity" stroke="#a0f8ff" strokeWidth={2} fill="url(#area)"/>
        </AreaChart></ResponsiveContainer></div>
      </section>
      <section className="panel compare dark"><h2>Sensor comparison</h2><p>{selected || 'Select a month'}</p><div className="chart"><ResponsiveContainer><BarChart data={[modis,viirs,noaa].map(key=>({name:names[key],count:selectedRow?.[key]}))}>
        <CartesianGrid vertical={false} stroke="#c5d1ff25"/><XAxis dataKey="name" tick={{fill:'#dce6ff',fontSize:10}}/><YAxis width={42} tick={{fill:'#dce6ff',fontSize:10}}/><Tooltip contentStyle={{background:'#242e59'}}/><Bar dataKey="count" name="Detections" fill="#a5b5ff" radius={[5,5,0,0]}/>
        </BarChart></ResponsiveContainer></div><small>Held-out monthly MAE: {format(errorMetric?.MAE)} detections</small></section>
      <section className="panel calendar"><div className="sectionhead"><div><h2><CalendarDays size={18}/> Burning calendar</h2><p>Select a month to inspect detections</p></div><label className="toggle"><input type="checkbox" checked={percent} onChange={e=>setPercent(e.target.checked)}/> Seasonal anomaly</label></div>
        <div className="calendar-scroll"><table><thead><tr><th>Year</th>{months.map(month=><th key={month}>{month}</th>)}</tr></thead><tbody>
          {years.filter(value=>year==='all'||year===value).map(value=><tr key={value}><th scope="row">{value}</th>{months.map((month,index)=>{
            const key=value+'-'+String(index+1).padStart(2,'0');
            const item=visible.find(row=>row.month===key);
            const n=percent?item?.[anomalyKey]:item?.[measure];
            const color=n==null?'#17204455':n<0?'#3d99c7':'#615cf5';
            return <td key={month}><button disabled={!item} type="button" aria-pressed={selected===key} aria-label={month+' '+value+': '+format(n)+(percent&&n!=null?' percent':'')}
              style={{backgroundColor:color,opacity:n == null ? .67 : Math.max(.48,Math.min(1,.48+Math.abs(n)/maximum))}}
              onClick={()=>setSelected(key)}>{format(n)}{percent&&n!=null?'%':''}</button></td>;
          })}</tr>)}
        </tbody></table></div>
        <small>{percent?'Percent departure from the median of at least two prior values for the same month. A zero median leaves the percentage blank.':'Counts of satellite detections. A dash indicates unavailable data.'}</small>
      </section>
      <section className="panel geo"><div className="sectionhead"><div><h2>Detection map</h2><p>{selected || 'Select a month'} · {map ? format(map.total)+' detections' : 'Monthly detections'}</p></div><label><span>Map product</span><select value={sensor} onChange={e=>setSensor(e.target.value)}>{[modis,viirs,noaa].map(key=><option key={key} value={key}>{names[key]}</option>)}</select></label></div>
        <DetectionMap cells={map?.cells ?? []} loading={!!selected&&!map&&!mapError}/>
        {mapError && <small role="alert">{mapError}</small>}
        {map && <small>{map.days} of {map.expected_days} daily partitions · <a href={base+'/monthly-hotspots?month='+selected+'&source='+sensor+'&csv=true'}>Download detections</a></small>}
      </section>
    </div>}
    <footer>NASA FIRMS observations · Hotspots can include repeated detections and non-fire thermal sources.</footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);
