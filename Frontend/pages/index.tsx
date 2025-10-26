import { Inter } from 'next/font/google'
import Header from './components/Header'
import Hero from './components/Hero'
import About from './components/About'
import LivekitMossVoiceAgent from './components/sampleusecase/Livekit-Moss-Voice Agent'
import TalkToYourPdf from './components/sampleusecase/TalkToYourPdf'
import InpersonaAgent from './components/sampleusecase/InpersonaAgent'
import Footer from './components/Footer'

const inter = Inter({ subsets: ['latin'] })

export default function Home() {
  return (
    <main className={inter.className}>
      <Header />
      <Hero />
      <About />
      <LivekitMossVoiceAgent />
      <TalkToYourPdf />
      <InpersonaAgent />
      <Footer />
    </main>
  )
}
