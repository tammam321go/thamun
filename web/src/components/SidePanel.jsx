import Evidence from './Evidence'
import Icon from './Icon'
import Impact from './Impact'
import Inspector from './Inspector'
import SystemPanel from './SystemPanel'

const TABS = [['decision', 'Decision'], ['evidence', 'Evidence'], ['impact', 'Impact'], ['system', 'System']]

export default function SidePanel({ tab, onTab, check, evidence, version, onClose }) {
  return (
    <div className="panel">
      <div className="side-head">
        <h2>Under the hood</h2>
        <button className="icon-btn close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
      </div>
      <div className="panel-tabs" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => onTab(id)}>{label}</button>
        ))}
      </div>
      {tab === 'decision' && <Inspector check={check} />}
      {tab === 'evidence' && <Evidence evidence={evidence} />}
      {tab === 'impact' && <Impact evidence={evidence} version={version} />}
      {tab === 'system' && <SystemPanel evidence={evidence} active={tab === 'system'} />}
    </div>
  )
}
