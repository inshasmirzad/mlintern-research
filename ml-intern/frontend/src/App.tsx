import { Box, CircularProgress } from '@mui/material';
import AppLayout from '@/components/Layout/AppLayout';
import LoginPage from '@/components/Auth/LoginPage';
import { useAuth } from '@/hooks/useAuth';
import { useAgentStore } from '@/store/agentStore';

function App() {
  // Non-blocking auth check — fires in background, updates store when done.
  // If auth fails later, apiFetch redirects to /auth/login.
  useAuth();
  
  const user = useAgentStore((s) => s.user);
  const isAuthLoading = useAgentStore((s) => s.isAuthLoading);

  if (isAuthLoading) {
    return (
      <Box sx={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex' }}>
      <AppLayout />
    </Box>
  );
}

export default App;
