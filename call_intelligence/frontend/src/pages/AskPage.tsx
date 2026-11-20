import { AskPanel } from '@/components/Ask'
import { Topbar } from '@/components/Shell'

export default function AskPage() {
  return <>
    <Topbar title="Ask" crumb="Questions about your calls, in English or Arabic" />
    <div className="content" style={{ maxWidth: 980 }}><AskPanel page /></div>
  </>
}
