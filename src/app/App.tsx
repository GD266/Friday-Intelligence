import Layout from '../layouts/Layout';

import './styles/globals.css';

export default function App() {
  return (
    <div className="min-h-screen bg-graphite-950">
      <Layout title="FRIDAY Intelligence" subtitle="Premium AI Desktop Workspace" />
      <div className="min-h-[400px] p-4">
        <p className="text-graphite-400 text-sm">
          FRIDAY Intelligence is running. Use the sidebar to navigate.
        </p>
      </div>
    </div>
  );
}