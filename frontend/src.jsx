import React, {useEffect, useRef, useState, useCallback} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, Bot, CalendarDays, Download, Flame, Layers, MapPin, Maximize2, Minimize2, Moon, Orbit, Sun} from 'lucide-react';
import {Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';
import {ChatProvider, useChat} from './context/ChatContext';
import ChatPanel from './components/chat/ChatPanel';

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

const osmAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function createImageryLayer(options) {
  return L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Imagery &copy; <a href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9">Esri and imagery providers</a>',
    maxNativeZoom: 19,
    maxZoom: 19,
    ...options,
  });
}

function DetectionMap({layers, enabled, loading, extent, place, vertices, drawing, onVertex, locateTrigger, children}) {
  const element = useRef(null);
  const map = useRef(null);
  useEffect(() => {
    const view = L.map(element.current, {scrollWheelZoom:true}).setView([7.8,80.7],7);
    const street = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: osmAttribution,
      maxZoom: 19,
    }).addTo(view);
    const terrain = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: osmAttribution + ', SRTM | &copy; <a href="https://opentopomap.org/about">OpenTopoMap (CC BY-SA)</a>',
      maxNativeZoom: 17,
      maxZoom: 19,
    });
    const satellite = createImageryLayer();
    const terrainSatellite = L.layerGroup([
      L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Hillshade &copy; Esri, Airbus DS, USGS, NGA, NASA, CGIAR, GEBCO and N Robinson',
        maxNativeZoom: 16,
        maxZoom: 19,
      }),
      createImageryLayer({opacity: .78}),
    ]);
    L.control.layers({
      'Street (OpenStreetMap)': street,
      'Terrain': terrain,
      'Satellite': satellite,
      'Terrain + Satellite': terrainSatellite,
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
              ...style, fill:false, dashArray:'5 4'
            })
          : L.circleMarker([cell.latitude,cell.longitude], {
              ...style, fillOpacity:.8, radius:Math.min(12,3+Math.sqrt(cell.count))
            });
        if (key === 'harmonized') {
          const countLabel = layer.factor != null ? 'estimated detections' : 'observed detections';
          shape.bindTooltip('5 km summary · ' + format(cell.count) + ' ' + countLabel)
            .bindPopup('5 km summary · ' + format(cell.count) + ' ' + countLabel + ' · ' + layer.status);
        } else {
          const hasDimensions = Number.isFinite(cell.scan) && cell.scan > 0 &&
            Number.isFinite(cell.track) && cell.track > 0;
          const width = hasDimensions ? cell.scan : key === modis ? 1 : .375;
          const height = hasDimensions ? cell.track : width;
          const position = L.latLng(cell.latitude, cell.longitude);
          // Convert kilometre dimensions to half-spans in degrees.
          const halfHeight = height / 222.39;
          const halfWidth = width / (222.39 * Math.max(.01, Math.cos(cell.latitude * Math.PI / 180)));
          const footprint = L.rectangle([
            [Math.max(-90, cell.latitude - halfHeight), cell.longitude - halfWidth],
            [Math.min(90, cell.latitude + halfHeight), cell.longitude + halfWidth],
          ], {...style, fillOpacity:.12, dashArray:'4 3', interactive:false});
          const popup = document.createElement('div');
          popup.textContent = [
            names[key] + ' · ' + format(cell.count) + ' detections at this location',
            cell.acquired_utc && 'Latest observation · ' + new Date(cell.acquired_utc).toISOString(),
            [cell.satellite, cell.confidence_class && cell.confidence_class + ' confidence'].filter(Boolean).join(' · '),
            position.lat.toFixed(5) + ', ' + position.lng.toFixed(5) + ' · pixel center',
            (hasDimensions ? 'Approximate footprint' : 'Nominal footprint') + ' · ' +
              format(width * 1000) + ' × ' + format(height * 1000) + ' m · orientation schematic',
          ].filter(Boolean).join('\n');
          popup.style.whiteSpace = 'pre-line';
          shape.bindTooltip(names[key] + ' · ' + format(cell.count) + ' detections')
            .bindPopup(popup)
            .on('popupopen', () => group.addLayer(footprint))
            .on('popupclose', () => group.removeLayer(footprint));
        }
        shape.addTo(group);
      }
    }
    return () => group.remove();
  }, [layers,enabled]);
  useEffect(() => {
    if (!map.current || !extent) return;
    map.current.invalidateSize();
    const [w,s,e,n] = extent.split(",").map(Number);
    if ([w,s,e,n].every(Number.isFinite) && w >= -180 && w < e && e <= 180 && s >= -90 && s < n && n <= 90) {
      map.current.fitBounds([[s,w],[n,e]], { padding: [15, 15], maxZoom: 11, animate: true });
    } else if (extent === 'world') {
      map.current.setView([0,0],2);
    }
  }, [extent, locateTrigger]);
  useEffect(() => {
    if (!place) return;
    const position = [place.lat, place.lon];
    map.current.setView(position, 12);
    const label = document.createElement('span');
    label.textContent = place.label;
    const marker = L.circleMarker(position, {radius:7, color:'#18386f', fillColor:'#fff', fillOpacity:1})
      .addTo(map.current).bindTooltip(label, {permanent:true});
    return () => marker.remove();
  }, [place]);
  useEffect(() => {
    if (!drawing) return;
    const add = event => onVertex([event.latlng.lng, event.latlng.lat]);
    map.current.on('click', add);
    return () => map.current.off('click', add);
  }, [drawing,onVertex]);
  useEffect(() => {
    const shape = L.polygon(vertices.map(([x,y]) => [y,x]), {color:'#864dff',interactive:false}).addTo(map.current);
    return () => shape.remove();
  }, [vertices]);
  return <div className="mapwrap"><div ref={element} className="map" aria-label="Map of recorded fire detections"/>
    {children}
    {loading && <span className="mapstatus">Loading detectionsâ€¦</span>}</div>;
}

function PlaceSearch({onSelect}) {
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);
  return <div className="place-search">
    <form onSubmit={async event => {
      event.preventDefault();
      const q = new FormData(event.currentTarget).get('place').trim();
      if (!q || loading) return;
      setResults([]);
      setStatus('');
      setLoading(true);
      try {
        const params = new URLSearchParams({q,limit:'5'});
        const response = await fetch('https://photon.komoot.io/api/?'+params, {
          signal:AbortSignal.timeout(10000)
        });
        if (!response.ok) throw new Error();
        const data = await response.json();
        const places = data.features.flatMap(({geometry, properties}) => {
          const [lon,lat] = geometry.coordinates;
          const label = [...new Set([properties.name, properties.city, properties.state,
            properties.country].filter(Boolean))].join(', ');
          return Number.isFinite(lat) && Number.isFinite(lon) && label ? [{lat,lon,label}] : [];
        });
        setResults(places);
        if (!places.length) setStatus('No matching places found.');
      } catch {
        setStatus('Place search is temporarily unavailable.');
      } finally {
        setLoading(false);
      }
    }}>
      <input name="place" type="search" aria-label="Search by place name" placeholder="Search by place name" required maxLength={120}/>
      <button type="submit" className="button" disabled={loading}>Search</button>
    </form>
    {(loading || status) && <small role="status">{loading ? 'Searching…' : status}</small>}
    {results.length > 0 && <ul aria-label="Search results">{results.map((place,index)=>
      <li key={index}><button type="button" className="button" onClick={()=>{
        onSelect(place);
        setResults([]);
      }}>{place.label}</button></li>)}</ul>}
  </div>;
}

function AssistantHeaderButton() {
  const { openChat, isOpen } = useChat();
  return (
    <button
      className="button ai-assistant-header-btn"
      type="button"
      aria-label="Open AI Assistant"
      aria-expanded={isOpen}
      onClick={openChat}
    >
      <Bot size={16} />
      <span>AI Assistant</span>
    </button>
  );
}

function AssistantFloatingPill() {
  const { openChat, isOpen } = useChat();
  if (isOpen) return null;
  return (
    <button
      className="chat-floating-button"
      type="button"
      aria-label="Open Satellite Fire AI Assistant"
      onClick={openChat}
    >
      <Flame size={18} />
      <span>Ask AI Assistant</span>
      <span className="pulse-dot" aria-hidden="true" />
    </button>
  );
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
  const polygon = vertices.length >= 3 ? vertices.map(pair=>pair.join(',')).join(';') : '';
  const polygonQuery = polygon ? '&polygon='+encodeURIComponent(polygon) : '';
  const [selected,setSelected] = useState(''), [sensor,setSensor] = useState(viirs);
  const [place, setPlace] = useState(null);
  const [controlsCollapsed, setControlsCollapsed] = useState(false);
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
  const [enabled,setEnabled] = useState([modis, viirs]);
  const [filter,setFilter] = useState(null);
  const [filterError,setFilterError] = useState('');
  const extent = regionInfo?.area ?? defaultExtent;
  const monthEnd = selected ? new Date(Date.UTC(+selected.slice(0,4),+selected.slice(5),0)).getUTCDate() : '';
  const defaults = {start:selected+'-01',end:selected+'-'+monthEnd,bbox:extent};
  const activeFilter = filter?.month === selected && filter.region === region ? filter : defaults;
  const [mapPresetRevision,setMapPresetRevision] = useState(0);
  const weekSlots = Array.from({length:Math.ceil(Number(monthEnd)/7)},(_,index)=> {
    const start = index*7+1;
    const end = Math.min(start+6,monthEnd);
    const date = day=>selected+'-'+String(day).padStart(2,'0');
    return {start:date(start),end:date(end),label:start+'–'+end};
  });
  const [mapResult,setMap] = useState(null), [error,setError] = useState(''), [mapError,setMapError] = useState('');
  function updateMapFilters(form) {
    const values = new FormData(form);
    const start = values.get('start'), end = values.get('end');
    const bbox = values.get('bbox').trim();
    const days = (Date.parse(end) - Date.parse(start)) / 86400000 + 1;
    const bounds = bbox.split(',').map(value => value.trim() ? Number(value) : NaN);
    const [w,s,e,n] = bounds;
    const [rw,rs,re,rn] = (extent === 'world' ? '-180,-90,180,90' : extent).split(',').map(Number);
    if (!Number.isFinite(days) || days < 1 || days > 31) {
      setFilterError('Choose an end date on or after the start date, within 31 days.');
      return;
    }
    if (bbox !== 'world' || extent !== 'world') {
      if (bounds.length !== 4 || !(rw <= w && w < e && e <= re && rs <= s && s < n && n <= rn)) {
        setFilterError('Enter west,south,east,north within the downloaded region.');
        return;
      }
    }
    setFilterError('');
    setFilter({region,month:selected,start,end,bbox});
  }
  const mapPath = '/map-layers?'+query+polygonQuery+'&'+new URLSearchParams({
    start:activeFilter.start,end:activeFilter.end,bbox:activeFilter.bbox
  });
  const map = mapResult?.region === region ? mapResult.data : null;
  const [percent,setPercent] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setVertices([]); setDrawing(false); setFilterError(''); setError(''); setRows([]); setSelected(''); setYear('all'); setPeriod({start:'',end:''}); setPeriodError('');
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
    setMapError('');
    get(mapPath,controller.signal).then(data => {
      if (!controller.signal.aborted) setMap({path:mapPath,region,data});
    })
      .catch(err => {if (!controller.signal.aborted) setMapError(err.message);});
    return () => controller.abort();
  }, [selected,mapPath]);
  const calendarPath = polygon ? '/polygon-calendar?'+query+polygonQuery : '';
  const [polygonCalendar,setPolygonCalendar] = useState(null);
  useEffect(() => {
    setPolygonCalendar(null);
    if (!calendarPath) return;
    const controller = new AbortController();
    get(calendarPath,controller.signal)
      .then(data => {
        if (!controller.signal.aborted) setPolygonCalendar({path:calendarPath,data});
      })
      .catch(err => {
        if (!controller.signal.aborted) setPolygonCalendar({path:calendarPath,error:err.message});
      });
    return () => controller.abort();
  }, [calendarPath]);
  const calendarResult = polygonCalendar?.path === calendarPath ? polygonCalendar : null;
  const calendarLoading = Boolean(calendarPath && !calendarResult);
  const [period,setPeriod] = useState({start:'',end:''});
  const [compareTrends,setCompareTrends] = useState(false);
  const [periodError,setPeriodError] = useState('');
  const years = [...new Set(rows.map(row => row.month.slice(0,4)))];
  const inSelectedPeriod = row => (year === 'all' || row.month.startsWith(year))
    && (!period.start || row.month >= period.start)
    && (!period.end || row.month <= period.end);
  const visible = rows.filter(inSelectedPeriod);
  const [calendarExpanded,setCalendarExpanded] = useState(false);
  const calendarRows = calendarPath ? (calendarResult?.data ?? []).filter(inSelectedPeriod) : visible;
  const calendarYears = [...new Set(calendarRows.map(row=>row.month.slice(0,4)))].sort().reverse();
  const displayedYears = calendarExpanded ? calendarYears : calendarYears.slice(0,5);
  useEffect(() => {
    if (visible.length && !visible.some(row => row.month === selected)) {
      setSelected(visible.at(-1).month);
    }
  }, [rows,year,period,selected]);
  const active = visible.filter(row => row[measure] != null);
  const selectedRow = rows.find(row => row.month === selected);
  const total = active.reduce((sum,row) => sum + row[measure],0);
  const peak = active.reduce((top,row) => !top || row[measure] > top[measure] ? row : top,null);
  const noaaMonths = rows.filter(row => row[noaa] != null).length;
  const anomalyKey = measure + '_anomaly';
  const maximum = Math.max(1,...calendarRows.map(row => percent ? Math.abs(row[anomalyKey] ?? 0) : row[measure] ?? 0));
  const chart = visible;
  const trendColors = theme === 'dark'
    ? {[modis]:'#ff9caf', [viirs]:'#ffd08a', harmonized:'#b3f5ff', [noaa]:'#f6b2e1'}
    : {[modis]:'#a11535', [viirs]:'#914000', harmonized:'#124ca7', [noaa]:'#8b185f'};
  const trendGrid = theme === 'dark' ? '#e2ebff40' : '#23345d38';
  const errorMetric = metrics.find(row => row.Method === 'Calibrated MODIS');
  const [locateTrigger, setLocateTrigger] = useState(0);

  const handleDispatchAction = useCallback((action) => {
    if (!action || !action.type) return;
    const payload = action.payload || {};

    if (action.type === 'show_on_map') {
      const targetRegion = payload.region || region;
      const targetBbox = payload.bbox || (regionInfo?.area ?? defaultExtent);

      if (payload.region && payload.region !== region) {
        setRegion(payload.region);
      }
      if (payload.start && payload.end) {
        const targetMonth = payload.start.slice(0, 7);
        const targetYear = targetMonth.slice(0, 4);

        // Ensure visible list includes this month so year filter doesn't overwrite selected
        setYear(prev => (prev !== 'all' && prev !== targetYear ? 'all' : prev));
        setPeriod({ start: '', end: '' });
        setSelected(targetMonth);

        setFilter({
          region: targetRegion,
          month: targetMonth,
          start: payload.start,
          end: payload.end,
          bbox: targetBbox,
        });
      }
      if (payload.layers && Array.isArray(payload.layers) && payload.layers.length > 0) {
        setEnabled(previous => [...new Set([...previous, ...payload.layers])]);
      }

      // Re-center / fitBounds on map
      setLocateTrigger(prev => prev + 1);

      // Smooth scroll viewport to the Detection Map and pulse highlight
      setTimeout(() => {
        const mapSection = document.querySelector('.geo');
        if (mapSection) {
          mapSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
          mapSection.classList.add('map-highlight-pulse');
          setTimeout(() => mapSection.classList.remove('map-highlight-pulse'), 2500);
        }
      }, 150);
    } else if (action.type === 'apply_filters') {
      if (payload.region) setRegion(payload.region);
      if (payload.year) setYear(payload.year);
      if (payload.measure) setMeasure(payload.measure);
    } else if (action.type === 'open_monthly_trend') {
      if (payload.month) setSelected(payload.month);
    }
  }, [region, regionInfo, extent]);

  return (
    <ChatProvider
      base={base}
      currentRegion={region}
      currentYear={year}
      currentMeasure={measure}
      currentExtent={activeFilter.bbox || extent}
      onDispatchAction={handleDispatchAction}
    >
      <main>
        <header><div className="brand"><img className="brand-logo" src={import.meta.env.BASE_URL + "spectrafuse-logo.png"} alt="" width="64" height="64" /><div><strong>SpectraFuse</strong><small>Satellite fire activity</small></div></div>
          <div className="filters"><label><span>Region</span><select value={region} onChange={e=>setRegion(e.target.value)}>
          {(regions.length ? regions : [{id:'sri-lanka',label:'Sri Lanka'}]).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label><span>Sensor basis</span><select value={measure} onChange={e=>setMeasure(e.target.value)}>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
          <label><span>Year</span><select value={year} onChange={e=>{const value=e.target.value;setYear(value);if(value!=='all')setSelected(rows.findLast(r=>r.month.startsWith(value))?.month ?? '');}}><option value="all">All years</option>{years.map(value=><option key={value}>{value}</option>)}</select></label></div>
          <div className="header-actions">
            <AssistantHeaderButton />
            <button className="button theme-button" type="button"
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              {theme === 'dark' ? <Sun size={17}/> : <Moon size={17}/>}
            </button>
            <a className="button" href={base+'/download?'+query+(year==='all' ? '' : '&year='+year)}><Download size={16}/> Monthly CSV</a>
          </div>
        </header>
    <section className="intro"><div><p className="location"><MapPin size={15}/> {regionInfo?.label ?? 'Sri Lanka'}</p><h1>Burning activity</h1><p>NASA FIRMS Â· Standard Processing Â· UTC</p></div>
    {!!rows.length && <form className="map-filters activity-period" key={region+period.start+period.end} onSubmit={event=>{
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      const start = values.get('start'), end = values.get('end');
      if (start && end && start > end) {
        setPeriodError('End month must be on or after start month.');
        return;
      }
      setPeriodError('');
      setYear('all');
      setPeriod({start,end});
    }}>
      <label>Start month<input type="month" name="start" defaultValue={period.start}/></label>
      <label>End month<input type="month" name="end" defaultValue={period.end}/></label>
      <button className="button" type="submit">Apply activity period</button>
      {(period.start || period.end) && <button className="button" type="button" onClick={()=>{
        setPeriodError('');
        setPeriod({start:'',end:''});
      }}>Clear activity period</button>}
      {periodError && <small role="alert">{periodError}</small>}
    </form>}
    </section>
    {!!rows.length && !visible.length && <p role="status">No monthly activity in the selected period.</p>}
    {error && <p role="alert" className="panel notice">{error}</p>}
    {!error && !rows.length && <p role="status" className="panel notice">Loading NASA FIRMS observationsâ€¦</p>}
    {!!rows.length && <div className="dashboard">
      <div className="dashboard-analytics">
      <section className="panel stat"><span><Layers size={17}/> Months with data</span><strong>{active.length}</strong><small>{visible[0]?.month} â€” {visible.at(-1)?.month}</small></section>
      <section className="panel stat"><span><Flame size={17}/> {names[measure]} detections</span><strong>{active.length ? format(total) : 'â€”'}</strong><small>Sum across selected months</small></section>
      <section className="panel stat dark"><span><Activity size={17}/> Peak activity</span><strong>{peak?.month ?? 'â€”'}</strong><small>{format(peak?.[measure])} detections</small></section>
      <section className="panel stat"><span><Orbit size={17}/> NOAA-20 coverage</span><strong>{noaaMonths}<em> / {rows.length}</em></strong><small>Complete months across the pilot</small></section>
      <section className="panel trend"><h2>Historical activity</h2><p>{compareTrends ? 'Monthly counts and VIIRS-scale activity' : names[measure]+' monthly activity'}</p>
        <label className="toggle"><input type="checkbox" checked={compareTrends}
          onChange={event=>setCompareTrends(event.target.checked)}/> Compare sensor trends</label>
        <div className="chart"><ResponsiveContainer><AreaChart data={chart} margin={{left:1,right:13,top:10,bottom:0}}>
          <CartesianGrid vertical={false} stroke={trendGrid}/><XAxis dataKey="month" tick={{fill:'var(--chart-label)',fontSize:11}} minTickGap={28}/><YAxis width={49} tick={{fill:'var(--chart-label)',fontSize:11}}/>
          <Tooltip contentStyle={{background:theme === 'dark' ? '#17213d' : '#fff',border:'1px solid #8ba0dd',borderRadius:10,color:'var(--chart-label)'}}
            cursor={{stroke:trendGrid}} formatter={(value,name)=>[format(value),name]}/>
          <Legend/>
          {(compareTrends ? primaryLayers : [measure]).map(key=><Area key={key} type="linear" dataKey={key} name={names[key]}
            stroke={trendColors[key]} strokeWidth={3} strokeDasharray={key==='harmonized'?'6 3':undefined}
            fill={trendColors[key]} fillOpacity={compareTrends ? 0 : .12}
            dot={{r:3, fill:trendColors[key], strokeWidth:0}}/>)}
        </AreaChart></ResponsiveContainer></div>
      </section>
      <section className="panel compare dark"><h2>Sensor comparison</h2><p>{selected || 'Select a month'}</p><div className="chart"><ResponsiveContainer><BarChart data={comparisonLayers.map(key=>({name:names[key],count:selectedRow?.[key]}))}>
        <CartesianGrid vertical={false} stroke="#c5d1ff25"/><XAxis dataKey="name" tick={{fill:'var(--chart-label)',fontSize:10}}/><YAxis width={42} tick={{fill:'var(--chart-label)',fontSize:10}}/><Tooltip contentStyle={{background:'#242e59'}}/><Bar dataKey="count" name="Detections" radius={[5,5,0,0]}>
          {comparisonLayers.map(key=><Cell key={key} fill={sensorColors[key].fill}/>)}
        </Bar>
        </BarChart></ResponsiveContainer></div>{selectedRow?.estimate_low != null && <p>Estimated from MODIS · empirical error range {format(selectedRow.estimate_low)}–{format(selectedRow.estimate_high)}</p>}
        <small>Held-out monthly MAE: {format(errorMetric?.MAE)} detections</small></section>
      </div>
      <section className={mapExpanded ? "panel geo geo-expanded" : "panel geo"}>
        <DetectionMap layers={map?.layers} enabled={enabled} vertices={vertices} drawing={drawing}
          onVertex={point=>setVertices(previous=>previous.length<100?[...previous,point]:previous)}
          extent={activeFilter.bbox} place={place} loading={!!selected&&mapResult?.path!==mapPath&&!mapError}
          locateTrigger={locateTrigger}>
        <div className="map-heading-actions">
        <label><span>Map product</span><select value={sensor} onChange={e=>{
          setSensor(e.target.value);
          setEnabled(previous=>[...new Set([...previous,e.target.value])]);
        }}>{comparisonLayers.map(key=><option key={key} value={key}>{names[key]}</option>)}</select></label>
        <button type="button" className="button map-expand" aria-pressed={mapExpanded}
          aria-label={mapExpanded ? 'Exit fullscreen map' : 'Fullscreen map'} title={mapExpanded ? 'Exit fullscreen' : 'Fullscreen map'}
          onClick={() => setMapExpanded(value => !value)}>
          {mapExpanded ? <Minimize2 size={16}/> : <Maximize2 size={16}/>}
        </button>
        </div>
        </DetectionMap>
        <div className="map-controls">
          {mapExpanded && <button type="button" className="button" aria-expanded={!controlsCollapsed}
            aria-controls="detection-map-controls" onClick={() => setControlsCollapsed(value => !value)}>
            {controlsCollapsed ? 'Show map controls' : 'Hide map controls'}
          </button>}
          <div id="detection-map-controls" hidden={mapExpanded && controlsCollapsed}>
          <div className="sectionhead"><div><h2>Detection map</h2>
        <p>{activeFilter.start} to {activeFilter.end} · {map?.provenance ?? 'NASA FIRMS Standard Processing'}</p></div>
        </div>
        <PlaceSearch onSelect={setPlace}/>
        <form className="map-filters" key={region+selected+locateTrigger+":"+mapPresetRevision} onSubmit={event=>event.preventDefault()}
          onChange={event=>{
            if (event.target.name === 'bbox') setFilterError('');
            else if (event.target.name) updateMapFilters(event.currentTarget);
          }}
          onBlur={event=>{
            if (event.target.name === 'bbox') updateMapFilters(event.currentTarget);
          }}>
          <label>Weekly time slot (UTC)<select
            value={weekSlots.find(slot=>slot.start===activeFilter.start && slot.end===activeFilter.end)?.start
              ?? (activeFilter.start===defaults.start && activeFilter.end===defaults.end ? 'month' : 'custom')}
            onChange={event=>{
              const slot = weekSlots.find(item=>item.start===event.target.value) ?? defaults;
              setFilter({month:selected,region,start:slot.start,end:slot.end,bbox:activeFilter.bbox});
              setFilterError('');
              setMapPresetRevision(value=>value+1);
            }}>
            <option value="month">Full month</option>
            {weekSlots.map((slot,index)=><option key={slot.start} value={slot.start}>Week {index+1} · {slot.label}</option>)}
            <option value="custom" disabled>Custom dates</option>
          </select></label>
          <label>Start date (UTC)<input name="start" type="date" required defaultValue={activeFilter.start}
            onChange={event=>{
              const start = event.target.value;
              const end = event.target.form.elements.namedItem('end');
              if (start && (end.value < start || Date.parse(end.value) - Date.parse(start) >= 31 * 86400000)) {
                end.value = start;
              }
            }}/></label>
          <label>End date (UTC)<input name="end" type="date" required defaultValue={activeFilter.end}/></label>
          <label>Bounding box<input name="bbox" required defaultValue={activeFilter.bbox}
            aria-label="Bounding box west,south,east,north"
            onKeyDown={event=>{if (event.key === 'Enter') event.currentTarget.blur();}}/></label>
        <div className="header-actions">
          <button type="button" className="button" onClick={() => {
            if (!drawing) setVertices([]);
            setDrawing(!drawing);
          }}>{drawing?'Stop drawing':'Draw polygon'}</button>
          {(drawing||vertices.length > 0) && <button type="button" className="button" onClick={() => {
            setDrawing(false);setVertices([]);
          }}>Clear</button>}
        </div>
        </form>
        {drawing && <small>Click three points to filter the map and calendar. Keep clicking to extend the area.</small>}
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
              {key === 'harmonized' ? 'Harmonized (5 km summary)' : names[key]}{layer && ' · '+layer.status+' · '+format(layer.total)}
              {layer && key!=='harmonized' && ' ('+layer.days+'/'+map.expected_days+' days)'}
            </label>;
          })}
        </div>
        {(filterError || mapError) && <small role="alert">{filterError || mapError}</small>}
        {map?.layers.harmonized.factor != null && <small>
          MODIS counts scaled by {format(map.layers.harmonized.factor)}. Regional monthly holdout
          90th-percentile absolute error: {format(map.layers.harmonized.monthly_error_p90)} detections.
          Cell-level uncertainty is unavailable.{' '}
        </small>}
        {map?.layers.harmonized.status === 'Observed by VIIRS' && <small>
          Harmonized cells contain observed S-NPP counts. Partition coverage cannot establish satellite coverage.{' '}
        </small>}
        {selected && sensor !== 'harmonized' && <small><a href={base+'/monthly-hotspots?month='+selected+'&source='+sensor+'&csv=true&'+query+polygonQuery}>Download calendar-month detections</a></small>}
          </div>
        </div>
      </section>
      <section className="panel calendar"><div className="sectionhead"><div><h2><CalendarDays size={18}/> Burning calendar</h2><p>{names[measure]}{polygon ? ' · Selected polygon' : ''} · Select a month to inspect detections</p></div><label className="toggle"><input type="checkbox" checked={percent} onChange={e=>setPercent(e.target.checked)}/> Seasonal anomaly</label></div>
        {calendarLoading && <p role="status">Updating calendar for the selected polygon…</p>}
        {calendarResult?.error && <p role="alert">{calendarResult.error}</p>}
        {calendarResult?.data && !calendarRows.length && <p role="status">No monthly data for the selected period.</p>}
        <div id="burning-calendar-table" className="calendar-scroll" aria-busy={calendarLoading}><table><thead><tr><th>Year</th>{months.map(month=><th key={month}>{month}</th>)}</tr></thead><tbody>
          {displayedYears.map(value=><tr key={value}><th scope="row">{value}</th>{months.map((month,index)=>{
            const key=value+'-'+String(index+1).padStart(2,'0');
            const item=calendarRows.find(row=>row.month===key);
            const n=percent?item?.[anomalyKey]:item?.[measure];
            const intensity=n==null?0:Math.min(1,Math.abs(n)/maximum);
            const color=n==null?'#17204455':`hsl(0 ${n<0?35:78}% ${43-19*intensity}%)`;
            return <td key={month}><button disabled={!item} type="button" aria-pressed={selected===key} title={item?.origin ?? 'Unavailable'} aria-label={month+' '+value+': '+format(n)+(percent&&n!=null?' percent':'')}
              style={{backgroundColor:color}}
              onClick={()=>setSelected(key)}>{format(n)}{percent&&n!=null?'%':''}</button></td>;
          })}</tr>)}
        </tbody></table></div>
        {calendarYears.length > 5 && <button type="button" className="button calendar-expand"
          aria-expanded={calendarExpanded} aria-controls="burning-calendar-table"
          onClick={()=>setCalendarExpanded(value=>!value)}>
          {calendarExpanded ? 'Show latest 5 years' : 'Show all '+calendarYears.length+' years'}
        </button>}
        <small>{percent?'Percent departure from the median of at least two prior values for the same month. A zero median leaves the percentage blank.':'Counts of satellite detections. A dash indicates unavailable data.'}</small>
      </section>
    </div>}
    <footer>NASA FIRMS observations Â· Hotspots can include repeated detections and non-fire thermal sources.</footer>
      </main>
      <AssistantFloatingPill />
      <ChatPanel onExecuteAction={handleDispatchAction} />
    </ChatProvider>
  );
}

createRoot(document.getElementById('root')).render(<App/>);
