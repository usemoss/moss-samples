import { useState, useRef, useEffect } from 'react'
import { Room, RoomEvent, createLocalAudioTrack, Track } from 'livekit-client'
import './VoiceAgent.css'

// URL of your token server
const TOKEN_SERVER_URL = 'http://localhost:8080/get-token'

// --- BEGIN METRICS DASHBOARD COMPONENTS ---

/**
 * A simple latency chart component using CSS bars
 */
const LatencyChart = ({ data, dataKey, label, unit = 'ms' }) => {
  if (!data || data.length === 0) return null;
  
  // Calculate max value for scaling, default to at least 100ms
  const values = data.map(d => {
    const val = d[dataKey] || 0;
    // Don't scale if dataKey suggests it's already in 'ms'
    if (dataKey.endsWith('_ms')) {
      return val;
    }
    return val * 1000; // convert seconds to ms
  });
  const maxVal = Math.max(...values, 100); 

  return (
    <div className="chart-container">
      <div className="chart-label">{label} (last {values.length} events)</div>
      <div className="chart-bars">
        {values.map((val, i) => (
          <div 
            key={i} 
            className="chart-bar" 
            style={{ height: `${(val / maxVal) * 100}%` }}
            title={`${val.toFixed(0)} ${unit}`}
          ></div>
        ))}
      </div>
    </div>
  );
};

/**
 * The main metrics dashboard bar
 */
const MetricsDashboard = ({ latestMetrics, sessionMetrics }) => {
  // Add 'moss' to the destructured props
  const { llm, tts, eou, moss } = latestMetrics;

  // Calculate total latency from the latest metrics (based on docs)
  const totalLatency = (eou?.end_of_utterance_delay || 0) + (llm?.ttft || 0) + (tts?.ttfb || 0);

  return (
    <div className="metrics-dashboard">
      {/* Top row for key KPIs */}
      <div className="metrics-kpis">
        <div className="kpi-item">
          <span className="kpi-label">Total Latency</span>
          <span className="kpi-value">{totalLatency > 0 ? `${(totalLatency * 1000).toFixed(0)} ms` : '-'}</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">LLM TTFT</span>
          <span className="kpi-value">{llm ? `${(llm.ttft * 1000).toFixed(0)} ms` : '-'}</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">TTS TTFB</span>
          <span className="kpi-value">{tts ? `${(tts.ttfb * 1000).toFixed(0)} ms` : '-'}</span>
        </div>
        {/* --- ADD MOSS KPI --- */}
        <div className="kpi-item">
          <span className="kpi-label">Moss Query</span>
          <span className="kpi-value">{moss ? `${moss.time_taken_ms.toFixed(0)} ms` : '-'}</span>
          <span className="kpi-sublabel">(matches: {moss ? moss.num_matches : '-'})</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">LLM Tokens</span>
          <span className="kpi-value">{llm ? `${llm.prompt_tokens} / ${llm.completion_tokens}` : '-'}</span>
          <span className="kpi-sublabel">(prompt / completion)</span>
        </div>
      </div>
      {/* Bottom row for charts */}
      <div className="metrics-charts">
        <LatencyChart data={sessionMetrics.llm} dataKey="ttft" label="LLM TTFT" />
        <LatencyChart data={sessionMetrics.tts} dataKey="ttfb" label="TTS TTFB" />
        <LatencyChart data={sessionMetrics.eou} dataKey="end_of_utterance_delay" label="EOU Delay" />
        {/* --- ADD MOSS CHART --- */}
        <LatencyChart data={sessionMetrics.moss} dataKey="time_taken_ms" label="Moss Query" />
      </div>
    </div>
  );
};

// --- END METRICS DASHBOARD COMPONENTS ---


function VoiceAgent() {
  const [status, setStatus] = useState('disconnected') // 'disconnected', 'connecting', 'connected', 'disconnecting', 'error'
  const [userName, setUserName] = useState('customer-' + Math.random().toString(36).substring(7))
  const [roomName, setRoomName] = useState('support-room')
  const [audioLevel, setAudioLevel] = useState(0)
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false)
  const [agentReady, setAgentReady] = useState(false)
  
  // --- BEGIN METRICS STATE (MODIFIED) ---
  const [sessionMetrics, setSessionMetrics] = useState({ llm: [], tts: [], eou: [], stt: [], moss: [] });
  const [latestMetrics, setLatestMetrics] = useState({ llm: null, tts: null, eou: null, stt: null, moss: null });
  // --- END METRICS STATE ---

  const roomRef = useRef(null)
  const audioElRef = useRef(null) // Ref for our persistent <audio> element
  const audioContextRef = useRef(null)

  const isConnected = status === 'connected';

  // Poll for agent readiness
  useEffect(() => {
    const checkReady = async () => {
      try {
        const res = await fetch('http://localhost:8080/ready')
        const data = await res.json()
        setAgentReady(data.ready)
      } catch (e) {
        setAgentReady(false)
      }
    }
    const interval = setInterval(checkReady, 2000)
    checkReady()
    return () => clearInterval(interval)
  }, [])

  /**
   * Fetches a token from the Python token server.
   */
  const getToken = async (roomName, identity) => {
    try {
      const response = await fetch(TOKEN_SERVER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          roomName: roomName,
          identity: identity,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(`Failed to get token: ${error.error}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('Token fetch error:', error)
      throw error
    }
  }

  // --- BEGIN METRICS RESET FUNCTION (MODIFIED) ---
  const resetMetrics = () => {
    setSessionMetrics({ llm: [], tts: [], eou: [], stt: [], moss: [] });
    setLatestMetrics({ llm: null, tts: null, eou: null, stt: null, moss: null });
  };
  // --- END METRICS RESET FUNCTION ---


  /**
   * Connects to the LiveKit room and handles all related events.
   */
  const connectToRoom = async () => {
    setStatus('connecting')
    resetMetrics(); // Reset metrics on new connection attempt

    try {
      const { token, url } = await getToken(roomName, userName)

      const room = new Room()
      roomRef.current = room

      // Ensure URL is in the correct WebSocket format
      const connectionUrl = url.startsWith('ws://') || url.startsWith('wss://') 
        ? url 
        : `ws://${url}`
      
      await room.connect(connectionUrl, token)
      setStatus('connected')
      console.log('✓ Successfully connected to LiveKit room')

      // --- BEGIN DATA CHANNEL LISTENER ---
      room.on(RoomEvent.DataReceived, (payload, participant, kind) => {

        // --- ADD THIS LINE FOR DEBUGGING ---
        console.log('Data packet received, kind:', kind);
        // -------------------------------------

        if (kind === 0) { // Check for the number 0 (reliable data channel)
          try {
            const decoder = new TextDecoder();
            const message = decoder.decode(payload);
            const metricsData = JSON.parse(message);

            // --- ADD THIS LINE FOR DEBUGGING ---
            console.log('Parsed metrics data:', metricsData);
            // -------------------------------------

            if (metricsData.type && metricsData.data) {
              // Update latest metric for KPI display
              setLatestMetrics(prev => ({ ...prev, [metricsData.type]: metricsData.data }));

              // Add to history for charts (only for relevant types)
              // --- ADD 'moss' to this list ---
              if (['llm', 'tts', 'eou', 'moss'].includes(metricsData.type)) {
                setSessionMetrics(prev => {
                  const history = prev[metricsData.type] || [];
                  // Add new data point
                  const newHistory = [...history, metricsData.data];
                  // Keep only the last 20 data points
                  if (newHistory.length > 20) newHistory.shift(); 
                  return { ...prev, [metricsData.type]: newHistory };
                });
              }
            }
          } catch (e) {
            console.error("Failed to parse metrics data:", e);
          }
        }
      });
      // --- END DATA CHANNEL LISTENER ---

      // Publish user's microphone
      const localAudioTrack = await createLocalAudioTrack()
      await room.localParticipant.publishTrack(localAudioTrack)
      
      // Monitor user's microphone audio level for UI feedback
      const audioTrack = localAudioTrack.mediaStreamTrack
      if (audioTrack) {
        audioContextRef.current = new AudioContext()
        const analyser = audioContextRef.current.createAnalyser()
        const microphone = audioContextRef.current.createMediaStreamSource(new MediaStream([audioTrack]))
        const dataArray = new Uint8Array(analyser.frequencyBinCount)
        analyser.fftSize = 256
        microphone.connect(analyser)

        const updateLevel = () => {
          if (!roomRef.current) return
          analyser.getByteFrequencyData(dataArray)
          const average = dataArray.reduce((a, b) => a + b) / dataArray.length
          setAudioLevel(Math.min(100, average))
          requestAnimationFrame(updateLevel)
        }
        updateLevel()
      }

      // Handle agent's audio track and speaking indication
      room.on(RoomEvent.TrackSubscribed, (track, publication) => {
        if (track.kind === 'audio') {
          console.log('✓ Subscribed to agent audio track')
          if (audioElRef.current) {
            track.attach(audioElRef.current)
            audioElRef.current.play().catch(e => console.error("Audio play failed:", e))
          }

          // --- ADD THIS CHECK ---
          if (publication) {
            publication.on(Track.Event.AudioLevelChanged, (level) => {
              setIsAgentSpeaking(level > 0.1) // Threshold for speaking detection
            })
            publication.on(Track.Event.Muted, () => setIsAgentSpeaking(false))
            publication.on(Track.Event.Unmuted, () => setIsAgentSpeaking(true))
          }
          // --- END OF CHECK ---
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, () => {
        setIsAgentSpeaking(false)
      })

      room.on(RoomEvent.Disconnected, (reason) => {
        console.log('Disconnected from room, reason:', reason)

        // Use enhanced cleanup
        cleanupRoom() // This will also reset metrics

        setStatus('disconnected')
        setIsAgentSpeaking(false)
      })

    } catch (error) {
      console.error('❌ Connection error:', error)
      setStatus(`error: ${error.message}`)
      
      // Auto-reset error status after 5 seconds
      setTimeout(() => {
        if (status.startsWith('error')) {
          setStatus('disconnected')
        }
      }, 5000)
    }
  }

  /**
   * Enhanced cleanup function for proper resource management
   */
  const cleanupRoom = () => {
    if (roomRef.current) {
      roomRef.current.removeAllListeners()
      roomRef.current.disconnect()
      roomRef.current = null
    }
    if (audioElRef.current) {
      audioElRef.current.pause()
      audioElRef.current.srcObject = null
      audioElRef.current.load()
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    resetMetrics(); // Reset metrics on cleanup
  }

  /**
   * Disconnects from the room.
   */
  const disconnectFromRoom = async () => {
    // Prevent multiple disconnects
    if (roomRef.current && status !== 'disconnecting') {
      setStatus('disconnecting')
      try {
        await roomRef.current.disconnect()
        // State updates (to 'disconnected') are handled by the 'Disconnected' room event
        // cleanupRoom() is called by the Disconnected event handler
      } catch (error) {
        console.error("Error during disconnect:", error)
        // Manually reset state if disconnect fails
        setStatus('disconnected')
        setIsAgentSpeaking(false)
        cleanupRoom() // Manually cleanup and reset metrics
      }
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupRoom()
    }
  }, [])

  return (
    <div className="voice-agent-container">
      <div className="card">
        <div className="header">
          <h1>Voice Agent</h1>
          <p className="subtitle">Powered by LiveKit & Moss AI</p>
        </div>

        <div className="status-section">
          <div className={`status-indicator ${status}`}>
            <span className="status-dot"></span>
            <span className="status-text">
              {status === 'disconnected' && (agentReady ? 'Ready to connect' : 'Agent initializing...')}
              {status === 'connecting' && 'Connecting...'}
              {status === 'disconnecting' && 'Disconnecting...'}
              {status === 'connected' && 'Connected - Speak freely!'}
              {status.startsWith('error') && status}
            </span>
          </div>

          {isConnected && (
            <div className="agent-status">
              <div className={`agent-speaking-indicator ${isAgentSpeaking ? 'speaking' : ''}`}>
                <span className="indicator-dot"></span>
                <span className="indicator-text">{isAgentSpeaking ? 'Agent Speaking' : 'Agent Listening'}</span>
              </div>
            </div>
          )}

          {isConnected && (
            <div className="audio-level">
              <div className="audio-level-label">Microphone Level:</div>
              <div className="audio-level-bar">
                <div 
                  className="audio-level-fill" 
                  style={{ width: `${audioLevel}%` }}
                ></div>
              </div>
            </div>
          )}
        </div>

        {!isConnected && (
          <div className="form-section">
            <div className="input-group">
              <label htmlFor="userName">Your Name:</label>
              <input
                id="userName"
                type="text"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                placeholder="Enter your name"
              />
            </div>

            <div className="input-group">
              <label htmlFor="roomName">Room Name:</label>
              <input
                id="roomName"
                type="text"
                value={roomName}
                onChange={(e) => setRoomName(e.target.value)}
                placeholder="Enter room name"
              />
            </div>
          </div>
        )}

        <div className="button-section">
          {!isConnected ? (
            <button
              className="connect-button"
              onClick={connectToRoom}
              disabled={status === 'connecting' || status === 'disconnecting' || !agentReady}
            >
              {status === 'connecting' ? 'Connecting...' : 
               !agentReady ? 'Agent initializing...' : 'Start Call'}
            </button>
          ) : (
            <button
              className="disconnect-button"
              onClick={disconnectFromRoom}
              disabled={status === 'disconnecting'}
            >
              {status === 'disconnecting' ? 'Ending Call...' : 'End Call'}
            </button>
          )}
        </div>

        {isConnected && (
          <div className="info-section">
            <p className="info-text">
              The agent is listening. Ask your question and it will respond.
            </p>
          </div>
        )}
      </div>

      {/* --- BEGIN METRICS DASHBOARD RENDER --- */}
      {isConnected && (
        <MetricsDashboard 
          latestMetrics={latestMetrics}
          sessionMetrics={sessionMetrics}
        />
      )}
      {/* --- END METRICS DASHBOARD RENDER --- */}

      {/* Persistent audio element for reliable playback */}
      <audio ref={audioElRef} autoPlay playsInline style={{ display: 'none' }} />

      <div className="footer">
        <p>Ensure the token server is running on port 8080</p>
      </div>
    </div>
  )
}

export default VoiceAgent