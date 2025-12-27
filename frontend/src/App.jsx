// Ficheiro: src/App.jsx (Limpo)
import React from 'react'
import { Outlet } from 'react-router-dom'

function App() {
  // O App.jsx agora só é responsável por renderizar 
  // o "filho" (seja o Login ou o DefaultLayout)
  return (
    <Outlet />
  )
}

export default App