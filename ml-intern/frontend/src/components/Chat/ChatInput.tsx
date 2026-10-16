import { useState, useCallback, useEffect, useRef, KeyboardEvent } from 'react';
import {
  Alert,
  Box,
  TextField,
  IconButton,
  CircularProgress,
  Chip,
  LinearProgress,
  Snackbar,
  Tooltip,
} from '@mui/material';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import StopIcon from '@mui/icons-material/Stop';
import AddIcon from '@mui/icons-material/Add';
import { apiFetch, apiUpload } from '@/utils/api';
import JobsUpgradeDialog from '@/components/JobsUpgradeDialog';
import { useAgentStore } from '@/store/agentStore';
import { useSessionStore } from '@/store/sessionStore';




const readApiErrorMessage = async (res: Response, fallback: string): Promise<string> => {
  try {
    const data = await res.json();
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail.message === 'string') return detail.message;
    if (detail && typeof detail.error === 'string') return detail.error;
  } catch {
    /* ignore malformed error bodies */
  }
  return fallback;
};

interface ChatInputProps {
  sessionId?: string;
  onSend: (text: string) => void;
  onStop?: () => void;
  onDatasetUploaded?: () => Promise<boolean> | boolean;
  isProcessing?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

interface DatasetUploadResponse {
  session_id: string;
  repo_id: string;
  repo_type: 'dataset';
  private: true;
  upload_id: string;
  config_name: string;
  filename: string;
  path_in_repo: string;
  size_bytes: number;
  format: 'csv' | 'json' | 'jsonl';
  hub_url: string;
  load_dataset_snippet: string;
}

const MAX_DATASET_UPLOAD_BYTES = 100 * 1024 * 1024;
const DATASET_UPLOAD_ACCEPT = '.csv,.json,.jsonl';
const DATASET_UPLOAD_EXTENSIONS = new Set(['csv', 'json', 'jsonl']);

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const datasetRepoUrl = (repoId: string) => (
  `https://huggingface.co/datasets/${repoId.split('/').map(encodeURIComponent).join('/')}`
);

export default function ChatInput({ sessionId, onSend, onStop, onDatasetUploaded, isProcessing = false, disabled = false, placeholder = 'Ask anything...' }: ChatInputProps) {
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sessionIdRef = useRef<string | undefined>(sessionId);
  const jobsUpgradeRequired = useAgentStore((s) => s.jobsUpgradeRequired);
  const setJobsUpgradeRequired = useAgentStore((s) => s.setJobsUpgradeRequired);
  const updateSessionModel = useSessionStore((s) => s.updateSessionModel);
  const [awaitingTopUp, setAwaitingTopUp] = useState(false);
  const [modelSwitchError, setModelSwitchError] = useState<string | null>(null);
  const [datasetUploadError, setDatasetUploadError] = useState<string | null>(null);
  const [datasetUploadSuccess, setDatasetUploadSuccess] = useState<string | null>(null);
  const [uploadedDatasets, setUploadedDatasets] = useState<DatasetUploadResponse[]>([]);
  const [isUploadingDataset, setIsUploadingDataset] = useState(false);
  const [datasetUploadProgress, setDatasetUploadProgress] = useState<number | null>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Model is per-session: fetch this tab's current model every time the
  // session changes. Other tabs keep their own selections independently.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    apiFetch(`/api/session/${sessionId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled) return;
        if (data?.model) {
          updateSessionModel(sessionId, data.model);
        }
      })
      .catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, [sessionId, updateSessionModel]);

  // Auto-focus the textarea when the session becomes ready
  useEffect(() => {
    if (!disabled && !isProcessing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [disabled, isProcessing]);

  const handleSend = useCallback(() => {
    if (input.trim() && !disabled && !isUploadingDataset) {
      onSend(input);
      setInput('');
    }
  }, [input, disabled, isUploadingDataset, onSend]);

  const handleDatasetUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleDatasetFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;

      if (!sessionId) {
        setDatasetUploadError('Start a session before uploading a dataset.');
        return;
      }

      const extension = file.name.split('.').pop()?.toLowerCase() || '';
      if (!DATASET_UPLOAD_EXTENSIONS.has(extension)) {
        setDatasetUploadError('Only CSV, JSON, and JSONL dataset files are supported.');
        return;
      }
      if (file.size > MAX_DATASET_UPLOAD_BYTES) {
        setDatasetUploadError(
          `Dataset files must be 100 MB or smaller. ${file.name} is ${formatBytes(file.size)}.`
        );
        return;
      }
      if (file.size === 0) {
        setDatasetUploadError('Uploaded dataset file is empty.');
        return;
      }

      const formData = new FormData();
      formData.append('file', file);
      setIsUploadingDataset(true);
      setDatasetUploadProgress(0);
      setDatasetUploadError(null);
      setDatasetUploadSuccess(null);
      try {
        const res = await apiUpload(`/api/session/${sessionId}/datasets`, formData, {
          onProgress: ({ percent }) => {
            setDatasetUploadProgress(percent !== null && percent < 100 ? percent : null);
          },
        });
        if (!res.ok) {
          setDatasetUploadError(await readApiErrorMessage(res, 'Dataset upload failed.'));
          return;
        }
        const payload = await res.json() as DatasetUploadResponse;
        setUploadedDatasets((previous) => [payload, ...previous]);
        setDatasetUploadSuccess(`Uploaded ${payload.filename} to ${payload.repo_id}`);
        await onDatasetUploaded?.();
      } catch (error) {
        setDatasetUploadError(
          error instanceof Error ? error.message : 'Dataset upload failed.'
        );
      } finally {
        setIsUploadingDataset(false);
        setDatasetUploadProgress(null);
      }
    },
    [sessionId, onDatasetUploaded],
  );

  useEffect(() => {
    if (!datasetUploadError) return;
    const timeout = window.setTimeout(() => setDatasetUploadError(null), 7000);
    return () => window.clearTimeout(timeout);
  }, [datasetUploadError]);

  useEffect(() => {
    if (!datasetUploadSuccess) return;
    const timeout = window.setTimeout(() => setDatasetUploadSuccess(null), 5000);
    return () => window.clearTimeout(timeout);
  }, [datasetUploadSuccess]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleJobsUpgradeClose = useCallback(() => {
    setJobsUpgradeRequired(null);
    setAwaitingTopUp(false);
  }, [setJobsUpgradeRequired]);

  const handleJobsUpgradeClick = useCallback(async () => {
    setAwaitingTopUp(true);
    if (!sessionId || !jobsUpgradeRequired) return;
    try {
      await apiFetch(`/api/pro-click/${sessionId}`, {
        method: 'POST',
        body: JSON.stringify({ source: 'hf_jobs_billing_dialog', target: 'hf_billing' }),
      });
    } catch {
      /* tracking is best-effort */
    }
  }, [sessionId, jobsUpgradeRequired]);

  const handleJobsRetry = useCallback(() => {
    const namespace = jobsUpgradeRequired?.namespace;
    setJobsUpgradeRequired(null);
    setAwaitingTopUp(false);
    const msg = namespace
      ? `I just added credits to the \`${namespace}\` namespace. Please retry the previous job.`
      : "I just added credits. Please retry the previous job.";
    onSend(msg);
  }, [jobsUpgradeRequired, setJobsUpgradeRequired, onSend]);

  // Auto-retry when the user comes back to this tab after clicking "Add credits".
  // Browsers fire visibilitychange when the tab regains focus from a sibling tab.
  useEffect(() => {
    if (!awaitingTopUp || !jobsUpgradeRequired) return;
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        handleJobsRetry();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [awaitingTopUp, jobsUpgradeRequired, handleJobsRetry]);

  return (
    <Box
      sx={{
        pb: { xs: 2, md: 4 },
        pt: { xs: 1, md: 2 },
        position: 'relative',
        zIndex: 10,
      }}
    >
      <Box sx={{ maxWidth: '880px', mx: 'auto', width: '100%', px: { xs: 0, sm: 1, md: 2 } }}>
        <Box
          className="composer"
          sx={{
            display: 'grid',
            gridTemplateColumns: 'auto 1fr auto',
            gridTemplateRows: 'auto auto',
            columnGap: '10px',
            rowGap: '4px',
            alignItems: 'end',
            bgcolor: 'var(--composer-bg)',
            borderRadius: 'var(--radius-md)',
            p: '12px',
            border: '1px solid var(--border)',
            transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
            '&:focus-within': {
                borderColor: 'var(--accent-yellow)',
                boxShadow: 'var(--focus)',
            }
          }}
        >
          <TextField
            fullWidth
            multiline
            maxRows={6}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || isProcessing}
            variant="standard"
            inputRef={inputRef}
            InputProps={{
                disableUnderline: true,
                sx: {
                    color: 'var(--text)',
                    fontSize: '15px',
                    fontFamily: 'inherit',
                    padding: 0,
                    lineHeight: 1.5,
                    minHeight: { xs: '44px', md: '56px' },
                    alignItems: 'flex-start',
                }
            }}
            sx={{
                gridColumn: '1 / -1',
                '& .MuiInputBase-root': {
                    p: 0,
                    backgroundColor: 'transparent',
                },
                '& textarea': {
                    resize: 'none',
                    padding: '0 !important',
                }
            }}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept={DATASET_UPLOAD_ACCEPT}
            onChange={handleDatasetFileChange}
            style={{ display: 'none' }}
          />
          <Box sx={{ gridColumn: '1', gridRow: '2', display: 'flex' }}>
            <Tooltip title="Upload dataset">
              <span>
                <IconButton
                  onClick={handleDatasetUploadClick}
                  disabled={disabled || isProcessing || isUploadingDataset || !sessionId}
                  sx={{
                    p: 1,
                    borderRadius: '50%',
                    color: uploadedDatasets.length ? 'var(--accent-yellow)' : 'var(--muted-text)',
                    transition: 'all 0.2s',
                    '&:hover': {
                      color: 'var(--accent-yellow)',
                      bgcolor: 'var(--hover-bg)',
                    },
                    '&.Mui-disabled': {
                      opacity: 0.3,
                    },
                  }}
                  aria-label="Upload dataset"
                >
                  <AddIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
          {isProcessing ? (
            <IconButton
              onClick={onStop}
              sx={{
                gridColumn: '3',
                gridRow: '2',
                justifySelf: 'end',
                p: 1.5,
                borderRadius: '10px',
                color: 'var(--muted-text)',
                transition: 'all 0.2s',
                position: 'relative',
                '&:hover': {
                  bgcolor: 'var(--hover-bg)',
                  color: 'var(--accent-red)',
                },
              }}
            >
              <Box sx={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CircularProgress size={28} thickness={3} sx={{ color: 'inherit', position: 'absolute' }} />
                <StopIcon sx={{ fontSize: 16 }} />
              </Box>
            </IconButton>
          ) : (
            <IconButton
              onClick={handleSend}
              disabled={disabled || isUploadingDataset || !input.trim()}
              sx={{
                gridColumn: '3',
                gridRow: '2',
                justifySelf: 'end',
                p: 1,
                borderRadius: '10px',
                color: 'var(--muted-text)',
                transition: 'all 0.2s',
                '&:hover': {
                  color: 'var(--accent-yellow)',
                  bgcolor: 'var(--hover-bg)',
                },
                '&.Mui-disabled': {
                  opacity: 0.3,
                },
              }}
            >
              <ArrowUpwardIcon fontSize="small" />
            </IconButton>
          )}
        </Box>
        {isUploadingDataset && (
          <Box sx={{ mt: 1, px: 0.5 }}>
            <LinearProgress
              variant={datasetUploadProgress === null ? 'indeterminate' : 'determinate'}
              value={datasetUploadProgress ?? 0}
              aria-label="Dataset upload progress"
              sx={{
                height: 4,
                borderRadius: 999,
                bgcolor: 'rgba(255,255,255,0.08)',
                '& .MuiLinearProgress-bar': {
                  borderRadius: 999,
                  bgcolor: 'var(--accent-yellow)',
                },
              }}
            />
          </Box>
        )}
        {(datasetUploadError || datasetUploadSuccess) && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
            <Alert
              severity={datasetUploadError ? 'error' : 'success'}
              variant="filled"
              onClose={() => {
                setDatasetUploadError(null);
                setDatasetUploadSuccess(null);
              }}
              sx={{ fontSize: '0.8rem', maxWidth: 520, width: '100%' }}
            >
              {datasetUploadError ?? datasetUploadSuccess}
            </Alert>
          </Box>
        )}
        {uploadedDatasets.length > 0 && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, justifyContent: 'center', mt: 1 }}>
            {uploadedDatasets.map((dataset) => (
              <Chip
                key={dataset.upload_id}
                size="small"
                label={`Dataset: ${dataset.filename}`}
                component="a"
                href={datasetRepoUrl(dataset.repo_id)}
                target="_blank"
                rel="noreferrer"
                clickable
                sx={{
                  maxWidth: '100%',
                  bgcolor: 'rgba(255,255,255,0.08)',
                  color: 'var(--text)',
                  border: '1px solid var(--divider)',
                  '& .MuiChip-label': {
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  },
                }}
              />
            ))}
          </Box>
        )}



        <JobsUpgradeDialog
          open={!!jobsUpgradeRequired}
          message={jobsUpgradeRequired?.message || ''}
          awaitingTopUp={awaitingTopUp}
          onClose={handleJobsUpgradeClose}
          onUpgrade={handleJobsUpgradeClick}
          onRetry={handleJobsRetry}
        />
        <Snackbar
          open={!!modelSwitchError}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          onClose={() => setModelSwitchError(null)}
          autoHideDuration={6000}
        >
          <Alert
            severity="error"
            variant="filled"
            onClose={() => setModelSwitchError(null)}
            sx={{ fontSize: '0.8rem', maxWidth: 480 }}
          >
            {modelSwitchError}
          </Alert>
        </Snackbar>
      </Box>
    </Box>
  );
}
