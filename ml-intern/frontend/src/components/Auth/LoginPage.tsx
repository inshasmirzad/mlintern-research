import React, { useState } from 'react';
import { Box, Button, TextField, Typography, Paper, Alert } from '@mui/material';
import { useAgentStore } from '@/store/agentStore';

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const setToken = useAgentStore((s) => s.setToken);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    async function safeParse(resp: Response) {
      try {
        return await resp.json();
      } catch (err) {
        try {
          const text = await resp.text();
          return { detail: text || `Server error: ${resp.status} ${resp.statusText}` };
        } catch (e) {
          return { detail: `Server error: ${resp.status} ${resp.statusText}` };
        }
      }
    }

    try {
      if (isLogin) {
        const res = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const data = await safeParse(res);
          throw new Error(data.detail || 'Login failed');
        }

        const data = await safeParse(res);
        setToken(data.access_token);
        // Page reload will trigger useAuth to fetch /auth/me
        window.location.reload();
      } else {
        const res = await fetch('/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, username }),
        });

        if (!res.ok) {
          const data = await safeParse(res);
          throw new Error(data.detail || 'Registration failed');
        }

        await safeParse(res);
        setIsLogin(true);
        setError('Registration successful. Please log in.');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'background.default' }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 400 }}>
        <Typography variant="h5" mb={3} textAlign="center">
          {isLogin ? 'Login to ML-Intern' : 'Register for ML-Intern'}
        </Typography>
        
        {error && <Alert severity={error.includes('successful') ? 'success' : 'error'} sx={{ mb: 2 }}>{error}</Alert>}
        
        <form onSubmit={handleSubmit}>
          {!isLogin && (
            <TextField
              fullWidth
              label="Username"
              margin="normal"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          )}
          <TextField
            fullWidth
            type="email"
            label="Email"
            margin="normal"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <TextField
            fullWidth
            type="password"
            label="Password"
            margin="normal"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          
          <Button
            fullWidth
            type="submit"
            variant="contained"
            size="large"
            sx={{ mt: 3, mb: 2 }}
            disabled={loading}
          >
            {loading ? 'Processing...' : (isLogin ? 'Login' : 'Register')}
          </Button>
          
          <Button
            fullWidth
            variant="text"
            onClick={() => { setIsLogin(!isLogin); setError(''); }}
          >
            {isLogin ? "Don't have an account? Register" : "Already have an account? Login"}
          </Button>
        </form>
      </Paper>
    </Box>
  );
}
