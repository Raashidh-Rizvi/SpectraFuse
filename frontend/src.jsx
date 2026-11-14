import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, CalendarDays, Download, Flame, Layers, MapPin, Maximize2, Minimize2, Moon, Orbit, Sun} from 'lucide-react';
import {Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';

const base = (import.meta.env.VITE_API_BASE_URL || '/api/fire').replace(/\/+$/, '');
const modis = 'MODIS_SP', viirs = 'VIIRS_SNPP_SP', noaa = 'VIIRS_NOAA20_SP';
const names = {[modis]:'MODIS raw', [viirs]:'VIIRS S-NPP raw', [noaa]:'VIIRS NOAA-20 raw', harmonized:'Harmonized'};
const sensorColors = {
  [modis]: {fill:'#e52e3e', stroke:'#7c1422'},
  [viirs]: {fill:'#ff861f', stroke:'#87300b'},
  harmonized: {fill:'#387df4', stroke:'#1854aa'},
  [noaa]: {fill:'#de3476', stroke:'#791743'},
};
const months = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ');
const format = n => n == null ? 'â€”' : new Intl.NumberFormat('en', {maximumFractionDigits:1}).format(n);

async function get(path, signal) {
  const response = await fetch(base + path, {signal});
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'Data could not be loaded. Check the filters and FastAPI connection.');
  }
  return response.json();
}

const primaryLayers = [modis, viirs, 'harmonized'];
const comparisonLayers = [...primaryLayers, noaa];
const defaultExtent = '79.5,5.8,82,10';

function DetectionMap({layers, enabled, loading, extent, vertices, drawing, onVertex}) {
  const element = useRef(null);
  const map = useRef(null);
  useEffect(() => {
    const view = L.map(element.current, {scrollWheelZoom:false}).setView([7.8,80.7],7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:'Â© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(view);
    map.current = view;
    const observer = new ResizeObserver(() => view.invalidateSize());
    observer.observe(element.current);
    return () => {observer.disconnect(); view.remove();};
  }, []);
  useEffect(() => {
    const group = L.layerGroup().addTo(map.current);
    for (const key of ['harmonized', modis, viirs, noaa]) {
      if (!enabled.includes(key)) continue;
      const layer = layers?.[key];
      const {fill, stroke} = sensorColors[key];
      for (const cell of layer?.features ?? []) {
        const style = {color:stroke, fillColor:fill, weight:1.5};
        const shape = key === 'harmonized'
          ? L.rectangle([[cell.south,cell.west],[cell.north,cell.east]], {
              ...style, fillOpacity:Math.min(.8,.22 + Math.log1p(cell.count)/8)
            })
          : L.circleMarker([cell.latitude,cell.longitude], {
              ...style, fillOpacity:.8, radius:Math.min(12,3+Math.sqrt(cell.count))
            });
        shape.bindTooltip(names[key] + ': ' + format(cell.count) +
          (key === 'harmonized' ? ' VIIRS-scale activity · ' + layer.status : ' detections')).addTo(group);
      }
    }
    return () => group.remove();
  }, [layers,enabled]);
  useEffect(() => {
    const [w,s,e,n] = extent.split(",").map(Number);
    if ([w,s,e,n].every(Number.isFinite) && w >= -180 && w < e && e <= 180 && s >= -90 && s < n && n <= 90) map.current.fitBounds([[s,w],[n,e]]);
    else if (extent === 'world') map.current.setView([0,0],2);
  }, [extent]);
  useEffect(() => {
    if (!drawing) return;
    const add = event => onVertex([event.latlng.lng, event.latlng.lat]);
    map.current.on('click', add);
    return () => map.current.off('click', add);
  }, [drawing,onVertex]);
  useEffect(() => {
    const shape = L.polygon(vertices.map(([x,y]) => [y,x]), {color:'#864dff'}).addTo(map.current);
    return () => shape.remove();
  }, [vertices]);
  return <div className="mapwrap"><div ref={element} className="map" aria-label="Map of recorded fire detections"/>
    {loading && <span className="mapstatus">Loading detectionsâ€¦</span>}</div>;
}

function App() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('firescope-theme');
    return saved === 'light' || saved === 'dark' ? saved :
      matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('firescope-theme', theme);
  }, [theme]);
  const [regions,setRegions] = useState([]);
  const [region,setRegion] = useState('sri-lanka');
  const regionInfo = regions.find(item => item.id === region);
  const query = 'region=' + encodeURIComponent(region);
  useEffect(() => {
    const controller = new AbortController();
    get('/regions',controller.signal).then(setRegions).catch(() => {});
    return () => controller.abort();
  }, []);
  const [rows,setRows] = useState([]), [metrics,setMetrics] = useState([]);
  const [year,setYear] = useState('all'), [measure,setMeasure] = useState('harmonized');
  const [drawing,setDrawing] = useState(false);
  const [vertices,setVertices] = useState([]);
  const [polygon,setPolygon] = useState('');
  const polygonQuery = polygon ? '&polygon='+encodeURIComponent(polygon) : '';
  const [selected,setSelected] = useState(''), [sensor,setSensor] = useState(viirs);
  const [mapExpanded, setMapExpanded] = useState(false);
  useEffect(() => {
    if (!mapExpanded) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const close = event => {
      if (event.key === 'Escape') setMapExpanded(false);
    };
    window.addEventListener('keydown', close);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener('keydown', close);
    };
  }, [mapExpanded]);
  const [enabled,setEnabled] = useState(primaryLayers);
  const [filter,setFilter] = useState(null);
  const extent = regionInfo?.area ?? defaultExtent;
  const monthEnd = selected ? new Date(Date.UTC(+selected.slice(0,4),+selected.slice(5),0)).getUTCDate() : '';
  const defaults = {start:selected+'-01',end:selected+'-'+monthEnd,bbox:extent};
  const activeFilter = filter?.month === selected && filter.region === region ? filter : defaults;
  const [mapResult,setMap] = useState(null), [error,setError] = useState(''), [mapError,setMapError] = useState('');
  const mapPath = '/map-layers?'+query+polygonQuery+'&'+new URLSearchParams({
    start:activeFilter.start,end:activeFilter.end,bbox:activeFilter.bbox
  });
  const map = mapResult?.path === mapPath ? mapResult.data : null;
  const [percent,setPercent] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setPolygon(''); setVertices([]); setDrawing(false); setError(''); setRows([]); setSelected(''); setYear('all');
    Promise.all([get('/dashboard?'+query,controller.signal),get('/sensor-comparison?'+query,controller.signal)])
      .then(([data,comparison]) => {
        setRows(data); setMetrics(comparison.metrics);
        setSelected(data.findLast(row => row[viirs] != null)?.month ?? data.at(-1)?.month ?? '');
      }).catch(err => {if (!controller.signal.aborted) setError(err.message);});
    return () => controller.abort();
  }, [query]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setMap(null); setMapError('');
    get(mapPath,controller.signal).then(data => {
      if (!controller.signal.aborted) setMap({path:mapPath,data});
    })
      .catch(err => {if (!controller.signal.aborted) setMapError(err.message);});
    return () => controller.abort();
  }, [selected,mapPath]);
  const years = [...new Set(rows.map(row => row.month.slice(0,4)))];
  const visible = rows.filter(row => year === 'all' || row.month.startsWith(year));
  const active = visible.filter(row => row[measure] != null);
  const selectedRow = rows.find(row => row.month === selected);
  const total = active.reduce((sum,row) => sum + row[measure],0);
  const peak = active.reduce((top,row) => !top || row[measure] > top[measure] ? row : top,null);
  const noaaMonths = rows.filter(row => row[noaa] != null).length;
  const anomalyKey = measure + '_anomaly';
  const maximum = Math.max(1,...visible.map(row => percent ? Math.abs(row[anomalyKey] ?? 0) : row[measure] ?? 0));
  const chart = visible;
  const errorMetric = metrics.find(row => row.Method === 'Calibrated MODIS');
  return <main>
    <header><div className="brand"><div className="mark"><Flame size={23}/></div><div><strong>SpectraFuse</strong><small>Satellite fire activity</small></div></div>
      <div className="header-actions"><button className="button theme-button" type="button"
        aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
        {theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}
      </button><a className="button" href={base+'/download?'+query+(year==='all' ? '' : '&year='+year)}><Download size={16}/> Monthly CSV</a></div></header>
    <section className="intro"><div><p className="location"><MapPin size={15}/> {regionInfo?.label ?? 'Sri Lanka'}</p><h1>Burning activity</h1><p>NASA FIRMS Â· Standard Processing Â· UTC</p></div>
      <div className="filters"><label><span>Region</span><select value={region} onChange={e=>setRegion(e.target.value)}>
      {(regions.length ? regions : [{id:'sri-lanka',label:'Sri Lanka'}]).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label><span>Sensor basis</span><select value={measure} onChange={e=>setMeasure(e.target.value)}>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
      <label><span>Year</span><select value={year} onChange={e=>{const value=e.target.value;setYear(value);if(value!=='all')setSelected(rows.findLast(r=>r.month.startsWith(value))?.month ?? '');}}><option value="all">All years</option>{years.map(value=><option key={value}>{value}</option>)}</select></label></div>
    </section>
    {error && <p role="alert" className="panel notice">{error}</p>}
    {!error && !rows.length && <p role="status" className="panel notice">Loading NASA FIRMS observationsâ€¦</p>}
    {!!rows.length && <div className="dashboard">
      <section className="panel stat"><span><Layers size={17}/> Months with data</span><strong>{active.length}</strong><small>{visible[0]?.month} â€” {visible.at(-1)?.month}</small></section>
      <section className="panel stat"><span><Flame size={17}/> {names[measure]} detections</span><strong>{active.length ? format(total) : 'â€”'}</strong><small>Sum across selected months</small></section>
      <section className="panel stat dark"><span><Activity size={17}/> Peak activity</span><strong>{peak?.month ?? 'â€”'}</strong><small>{format(peak?.[measure])} detections</small></section>
      <section className="panel stat"><span><Orbit size={17}/> NOAA-20 coverage</span><strong>{noaaMonths}<em> / {rows.length}</em></strong><small>Complete months across the pilot</small></section>
      <section className="panel trend"><h2>Historical activity</h2><p>Monthly counts and VIIRS-scale activity</p>
        <div className="chart"><ResponsiveContainer><AreaChart data={chart} margin={{left:1,right:13,top:10,bottom:0}}>
          <CartesianGrid vertical={false} stroke="#c5d1ff35"/><XAxis dataKey="month" tick={{fill:'var(--chart-label)',fontSize:11}} minTickGap={28}/><YAxis width={49} tick={{fill:'var(--chart-label)',fontSize:11}}/>
          <Tooltip contentStyle={{background:'#1b2450',border:'1px solid #8ba0dd',borderRadius:10}} formatter={(value,name)=>[format(value),name]}/>
          <Legend/>
          {primaryLayers.map(key=><Area key={key} type="linear" dataKey={key} name={names[key]}
            stroke={sensorColors[key].fill} strokeWidth={2} strokeDasharray={key==='harmonized'?'5 3':undefined} fill="none"/>)}
        </AreaChart></ResponsiveContainer></div>
      </section>
      <section className="panel compare dark"><h2>Sensor comparison</h2><p>{selected || 'Select a month'}</p><div className="chart"><ResponsiveContainer><BarChart data={comparisonLayers.map(key=>({name:names[key],count:selectedRow?.[key]}))}>
        <CartesianGrid vertical={false} stroke="#c5d1ff25"/><XAxis dataKey="name" tick={{fill:'var(--chart-label)',fontSize:10}}/><YAxis width={42} tick={{fill:'var(--chart-label)',fontSize:10}}/><Tooltip contentStyle={{background:'#242e59'}}/><Bar dataKey="count" name="Detections" radius={[5,5,0,0]}>
          {comparisonLayers.map(key=><Cell key={key} fill={sensorColors[key].fill}/>)}
        </Bar>
        </BarChart></ResponsiveContainer></div>{selectedRow?.estimate_low != null && <p>Estimated from MODIS · empirical error range {format(selectedRow.estimate_low)}–{format(selectedRow.estimate_high)}</p>}
        <small>Held-out monthly MAE: {format(errorMetric?.MAE)} detections</small></section>
      <section className="panel calendar"><div className="sectionhead"><div><h2><CalendarDays size={18}/> Burning calendar</h2><p>Select a month to inspect detections</p></div><label className="toggle"><input type="checkbox" checked={percent} onChange={e=>setPercent(e.target.checked)}/> Seasonal anomaly</label></div>
        <div className="calendar-scroll"><table><thead><tr><th>Year</th>{months.map(month=><th key={month}>{month}</th>)}</tr></thead><tbody>
          {years.filter(value=>year==='all'||year===value).map(value=><tr key={value}><th scope="row">{value}</th>{months.map((month,index)=>{
            const key=value+'-'+String(index+1).padStart(2,'0');
            const item=visible.find(row=>row.month===key);
            const n=percent?item?.[anomalyKey]:item?.[measure];
            const intensity=n==null?0:Math.min(1,Math.abs(n)/maximum);
            const color=n==null?'#17204455':`hsl(0 ${n<0?35:78}% ${43-19*intensity}%)`;
            return <td key={month}><button disabled={!item} type="button" aria-pressed={selected===key} title={item?.origin ?? 'Unavailable'} aria-label={month+' '+value+': '+format(n)+(percent&&n!=null?' percent':'')}
              style={{backgroundColor:color}}
              onClick={()=>setSelected(key)}>{format(n)}{percent&&n!=null?'%':''}</button></td>;
          })}</tr>)}
        </tbody></table></div>
        <small>{percent?'Percent departure from the median of at least two prior values for the same month. A zero median leaves the percentage blank.':'Counts of satellite detections. A dash indicates unavailable data.'}</small>
      </section>
      <section className={mapExpanded ? "panel geo geo-expanded" : "panel geo"}><div className="sectionhead"><div><h2>Detection map</h2>
        <p>{selected || 'Select a month'} · {map?.provenance ?? 'NASA FIRMS Standard Processing'}</p></div>
        <label><span>Map product</span><select value={sensor} onChange={e=>{
          setSensor(e.target.value);
          setEnabled(previous=>[...new Set([...previous,e.target.value])]);
        }}>{comparisonLayers.map(key=><option key={key} value={key}>{names[key]}</option>)}</select></label></div>
        <button type="button" className="button map-expand" aria-pressed={mapExpanded}
          onClick={() => setMapExpanded(value => !value)}>
          {mapExpanded ? <Minimize2 size={16}/> : <Maximize2 size={16}/>}
          {mapExpanded ? 'Exit fullscreen' : 'Fullscreen map'}
        </button>
        <form className="map-filters" key={region+selected+extent} onSubmit={event=>{
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          setFilter({region,month:selected,start:values.get('start'),end:values.get('end'),bbox:values.get('bbox').trim()});
        }}>
          <label>Start date (UTC)<input name="start" type="date" required defaultValue={activeFilter.start}/></label>
          <label>End date (UTC)<input name="end" type="date" required defaultValue={activeFilter.end}/></label>
          <label>Bounding box<input name="bbox" required defaultValue={activeFilter.bbox}
            aria-label="Bounding box west,south,east,north"/></label>
          <button type="submit" className="button">Apply filters</button>
        </form>
        <div className="header-actions">
          <button type="button" className="button" onClick={() => {
            if (drawing) setPolygon(vertices.map(pair=>pair.join(',')).join(';'));
            else {setVertices([]);setPolygon('');}
            setDrawing(!drawing);
          }} disabled={drawing&&vertices.length<3}>{drawing?'Apply polygon':'Draw polygon'}</button>
          {(drawing||polygon) && <button type="button" className="button" onClick={() => {
            setDrawing(false);setVertices([]);setPolygon('');
          }}>Clear</button>}
        </div>
        {drawing && <small>Click at least three points on the map, then apply.</small>}
        <div className="sensor-legend" aria-label="Map layers">
          {comparisonLayers.map(key=>{
            const {fill,stroke} = sensorColors[key];
            const layer = map?.layers[key];
            return <label key={key} data-active={sensor===key}>
              <input type="checkbox" checked={enabled.includes(key)} onChange={event=>{
                const checked = event.target.checked;
                setEnabled(previous=>checked ? [...previous,key] : previous.filter(item=>item!==key));
              }}/>
              <i aria-hidden="true" style={{background:fill,borderColor:stroke,borderRadius:key==='harmonized'?0:'50%'}}/>
              {names[key]}{layer && ' · '+layer.status+' · '+format(layer.total)}
              {layer && key!=='harmonized' && ' ('+layer.days+'/'+map.expected_days+' days)'}
            </label>;
          })}
        </div>
        <DetectionMap layers={map?.layers} enabled={enabled} vertices={vertices} drawing={drawing}
          onVertex={point=>setVertices(previous=>previous.length<100?[...previous,point]:previous)}
          extent={activeFilter.bbox} loading={!!selected&&!map&&!mapError}/>
        {mapError && <small role="alert">{mapError}</small>}
        {map?.layers.harmonized.factor != null && <small>
          MODIS counts scaled by {format(map.layers.harmonized.factor)}. Regional monthly holdout
          90th-percentile absolute error: {format(map.layers.harmonized.monthly_error_p90)} detections.
          Cell-level uncertainty is unavailable.
        </small>}
        {map?.layers.harmonized.status === 'Observed by VIIRS' && <small>
          Harmonized cells contain observed S-NPP counts. Partition coverage cannot establish satellite coverage.
        </small>}
        {selected && sensor !== 'harmonized' && <small><a href={base+'/monthly-hotspots?month='+selected+'&source='+sensor+'&csv=true&'+query+polygonQuery}>Download calendar-month detections</a></small>}
      </section>
    </div>}
    <footer>NASA FIRMS observations Â· Hotspots can include repeated detections and non-fire thermal sources.</footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App/>);
