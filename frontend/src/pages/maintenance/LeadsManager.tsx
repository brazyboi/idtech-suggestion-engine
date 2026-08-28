import { useEffect, useState } from 'react';

interface Lead {
  id: number;
  name: string | null;
  email: string | null;
  company: string | null;
  phone: string | null;
  status: string;
  created_at: string | null;
  qualification: Record<string, unknown> | null;
  products_shown: Record<string, unknown> | null;
}

export default function LeadsManager() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  useEffect(() => {
    const fetchLeads = async () => {
      try {
        const res = await fetch('/api/lead/leads');
        if (!res.ok) throw new Error(`Failed to fetch leads: ${res.statusText}`);
        const data: Lead[] = await res.json();
        setLeads(data);
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    };
    fetchLeads();
  }, []);

  if (loading) return <div className='text-primary p-10'><h1>Loading leads...</h1></div>;
  if (error) return <div className='text-primary p-10'><h1>Error: {error}</h1></div>;

  return (
    <div className='p-10' style={{ color: 'var(--text-primary)' }}>
      <h1 className='text-2xl font-bold mb-4'>Lead Management</h1>
      <a href='/admin' className='underline block mb-4' style={{ color: 'var(--text-link, #3b82f6)' }}>
        &larr; Back to Dashboard
      </a>

      {selectedLead ? (
        <div>
          <button
            onClick={() => setSelectedLead(null)}
            className='underline mb-4'
            style={{ color: 'var(--text-link, #3b82f6)' }}
          >
            &larr; Back to list
          </button>
          <div className='rounded-lg border p-6 max-w-lg' style={{ borderColor: 'var(--border)' }}>
            <h2 className='text-xl font-semibold mb-3'>Lead #{selectedLead.id}</h2>
            <table className='w-full text-sm'>
              <tbody>
                <tr><td className='font-medium pr-4 py-1'>Name</td><td>{selectedLead.name || '—'}</td></tr>
                <tr><td className='font-medium pr-4 py-1'>Email</td><td>{selectedLead.email || '—'}</td></tr>
                <tr><td className='font-medium pr-4 py-1'>Company</td><td>{selectedLead.company || '—'}</td></tr>
                <tr><td className='font-medium pr-4 py-1'>Phone</td><td>{selectedLead.phone || '—'}</td></tr>
                <tr><td className='font-medium pr-4 py-1'>Status</td><td><span className='rounded-full bg-yellow-100 text-yellow-800 px-2 py-0.5 text-xs'>{selectedLead.status}</span></td></tr>
                <tr><td className='font-medium pr-4 py-1'>Created</td><td>{selectedLead.created_at ? new Date(selectedLead.created_at).toLocaleString() : '—'}</td></tr>
              </tbody>
            </table>
            {selectedLead.qualification && (
              <div className='mt-4'>
                <h3 className='font-medium mb-1'>Qualification Data</h3>
                <pre className='rounded p-3 text-xs overflow-auto max-h-60' style={{ background: 'var(--bg-secondary, #f5f5f5)' }}>
                  {JSON.stringify(selectedLead.qualification, null, 2)}
                </pre>
              </div>
            )}
            {selectedLead.products_shown && (
              <div className='mt-4'>
                <h3 className='font-medium mb-1'>Products Shown</h3>
                <pre className='rounded p-3 text-xs overflow-auto max-h-40' style={{ background: 'var(--bg-secondary, #f5f5f5)' }}>
                  {JSON.stringify(selectedLead.products_shown, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <p className='mb-4 text-sm' style={{ color: 'var(--text-secondary, #666)' }}>
            Showing {leads.length} lead(s). Click a lead to view details.
          </p>
          <div className='overflow-x-auto'>
            <table className='w-full text-sm border-collapse'>
              <thead>
                <tr className='text-left' style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className='pb-2 pr-4 font-medium'>ID</th>
                  <th className='pb-2 pr-4 font-medium'>Name</th>
                  <th className='pb-2 pr-4 font-medium'>Email</th>
                  <th className='pb-2 pr-4 font-medium'>Company</th>
                  <th className='pb-2 pr-4 font-medium'>Status</th>
                  <th className='pb-2 font-medium'>Date</th>
                </tr>
              </thead>
              <tbody>
                {leads.length === 0 ? (
                  <tr>
                    <td colSpan={6} className='pt-4 text-center' style={{ color: 'var(--text-secondary, #666)' }}>
                      No leads captured yet. Start a conversation with the bot!
                    </td>
                  </tr>
                ) : (
                  leads.map((lead) => (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className='cursor-pointer hover:opacity-80'
                      style={{ borderBottom: '1px solid var(--border)' }}
                    >
                      <td className='py-2 pr-4'>{lead.id}</td>
                      <td className='py-2 pr-4'>{lead.name || '—'}</td>
                      <td className='py-2 pr-4'>{lead.email || '—'}</td>
                      <td className='py-2 pr-4'>{lead.company || '—'}</td>
                      <td className='py-2 pr-4'>
                        <span
                          className='rounded-full px-2 py-0.5 text-xs'
                          style={{
                            background: lead.status === 'new' ? '#e0f2fe' : lead.status === 'escalated' ? '#fef3c7' : '#f3e8ff',
                            color: lead.status === 'new' ? '#0369a1' : lead.status === 'escalated' ? '#92400e' : '#6b21a8',
                          }}
                        >
                          {lead.status}
                        </span>
                      </td>
                      <td className='py-2'>{lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}