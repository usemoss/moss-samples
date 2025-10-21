import { useState, useRef, useEffect } from 'react'
import { Room, RoomEvent, createLocalAudioTrack, Track } from 'livekit-client'
import './VoiceAgent.css'

// URL of your token server
const TOKEN_SERVER_URL = 'http://localhost:8080/get-token'

function VoiceAgent() {
  const [status, setStatus] = useState('disconnected') // 'disconnected', 'connecting', 'connected', 'error'
  const [userName, setUserName] = useState('customer-' + Math.random().toString(36).substring(7))
  const [roomName, setRoomName] = useState('support-room')
  const [audioLevel, setAudioLevel] = useState(0)
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false)
  
  const roomRef = useRef(null)
  const audioElRef = useRef(null) // Ref for our persistent <audio> element

  const isConnected = status === 'connected';

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

  /**
   * Connects to the LiveKit room and handles all related events.
   */
  const connectToRoom = async () => {
    setStatus('connecting')

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

      // Publish user's microphone
      const localAudioTrack = await createLocalAudioTrack()
      await room.localParticipant.publishTrack(localAudioTrack)
      
      // Monitor user's microphone audio level for UI feedback
      const audioTrack = localAudioTrack.mediaStreamTrack
      if (audioTrack) {
        const audioContext = new AudioContext()
        const analyser = audioContext.createAnalyser()
        const microphone = audioContext.createMediaStreamSource(new MediaStream([audioTrack]))
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

          publication.on(Track.Event.AudioLevelChanged, (level) => {
            setIsAgentSpeaking(level > 0.1) // Threshold for speaking detection
          })
          publication.on(Track.Event.Muted, () => setIsAgentSpeaking(false))
          publication.on(Track.Event.Unmuted, () => setIsAgentSpeaking(true))
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, () => {
        setIsAgentSpeaking(false)
      })

      room.on(RoomEvent.Disconnected, (reason) => {
        console.log('Disconnected from room, reason:', reason)
        setStatus('disconnected')
        setIsAgentSpeaking(false)
        roomRef.current = null
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
   * Disconnects from the room.
   */
  const disconnectFromRoom = async () => {
    if (roomRef.current) {
      await roomRef.current.disconnect()
      // State updates are handled by the 'Disconnected' room event
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect()
      }
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
              {status === 'disconnected' && 'Disconnected'}
              {status === 'connecting' && 'Connecting...'}
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
              disabled={status === 'connecting'}
            >
              {status === 'connecting' ? 'Connecting...' : 'Start Call'}
            </button>
          ) : (
            <button
              className="disconnect-button"
              onClick={disconnectFromRoom}
            >
              End Call
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

      {/* Persistent audio element for reliable playback */}
      <audio ref={audioElRef} autoPlay playsInline style={{ display: 'none' }} />

      <div className="footer">
        <p>Ensure the token server is running on port 8080</p>
      </div>
    </div>
  )
}

export default VoiceAgent

