from pathlib import Path
class M3UExporter:
    ORDER=('tvg-id','tvg-name','tvg-logo','group-title')
    def render(self,channels):
        lines=['#EXTM3U']
        for c in channels:
            a=dict(c.attributes)
            if c.tvg_id:a['tvg-id']=c.tvg_id
            if c.tvg_name:a['tvg-name']=c.tvg_name
            if c.logo:a['tvg-logo']=c.logo
            if c.group:a['group-title']=c.group
            keys=[k for k in self.ORDER if k in a]+sorted(k for k in a if k not in self.ORDER)
            attrs=' '.join(f'{k}="{a[k].replace(chr(34),chr(39))}"' for k in keys)
            lines.append(f'#EXTINF:-1{(" "+attrs) if attrs else ""},{c.name}')
            lines.extend(c.extra_directives); lines.append(c.stream_url)
        return '\n'.join(lines)+'\n'
    def write(self,path:Path,channels): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(self.render(channels),encoding='utf-8')
