import { useState } from 'react'
import './App.css'
import Manage from './Manage'
import Search from './Search'

// Shell SPA: tab tìm kiếm (Story 3.1) + tab quản lý kho/ingest (requeue từ UI).
function App() {
  const [tab, setTab] = useState<'search' | 'manage'>('search')

  return (
    <div className="app">
      <h1>Scene Intelligence</h1>
      <nav className="tabs">
        <button
          className={tab === 'search' ? 'active' : ''}
          onClick={() => setTab('search')}
        >
          Tìm kiếm
        </button>
        <button
          className={tab === 'manage' ? 'active' : ''}
          onClick={() => setTab('manage')}
        >
          Quản lý kho
        </button>
      </nav>
      {tab === 'search' ? <Search /> : <Manage />}
    </div>
  )
}

export default App
