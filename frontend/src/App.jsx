import { PipelineProvider, usePipelineContext } from './context/PipelineContext';
import UploadView from './components/upload/UploadView';
import PipelineView from './components/pipeline/PipelineView';
import ResultView from './components/result/ResultView';

function AppContent() {
  const { state } = usePipelineContext();
  switch (state.phase) {
    case 'idle':     return <UploadView />;
    case 'complete': return <ResultView />;
    default:         return <PipelineView />; // 'running', 'hitl_paused', 'error'
  }
}

export default function App() {
  return (
    <PipelineProvider>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <AppContent />
      </div>
    </PipelineProvider>
  );
}
