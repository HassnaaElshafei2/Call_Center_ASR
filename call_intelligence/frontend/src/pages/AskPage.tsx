import { AskPanel } from '@/components/Ask'
import { Topbar } from '@/components/Shell'

export default function AskPage() {
  return <>
    <Topbar title={<>Ask <span className="brand-name">Sia</span></>} crumb="Questions about your calls, in English or Arabic" />
    <div className="content"><AskPanel page /></div>
  </>
}
