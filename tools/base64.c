/* base64 command for Unix V6 on PDP-11 */
/* usage similar to the MacOS command */
/* written in pre-K&R C */

int ibuf[259];		/* struct buf */
int obuf[259];
int wrap;

main(argc,argv)
int argc;
char *argv[];
{
	int i;
	int decode;

	decode = 0;
	wrap = 76;

	ibuf[0] = 0;	    /* standard input */
	obuf[0] = 1;	    /* standard output */

	for(i=1; i<argc; ++i) {
		if(argv[i][0]!='-' || argv[i][2])
			goto unknown;

		switch(argv[i][1]) {
		case 'h':
			diag("Usage:	base64 [-h] [-D] [-b num] [-i fn] [-o fn]\n");
			diag("	-h	display this message and exit\n");
			diag("	-D	decode input\n");
			diag("	-b	break encoded string into num character lines\n");
			diag("	-i	input file name\n");
			diag("	-o	output file name\n");
			return;
		case 'D':
			decode = 1;
			break;
		case 'b':
			wrap = atoi(argv[++i]);
			break;
		case 'o':
			if ((obuf[0] = creat(argv[++i], 0666)) < 0) {
				diag(argv[i]);
				diag(": failed to create\n");
				return;
			}
			break;
		case 'i':
			if (fopen(argv[++i], ibuf) < 0) {
				diag(argv[i]);
				diag(": failed to open\n");
				return;
			}
			break;
		default:
		unknown:
			diag(argv[i]);
			diag(": unknown parameter\n");
			return;
		}
	}

	if (decode)
		decode_base64();
	else
		encode_base64();

	fflush(obuf);
	close(ibuf[0]);
	close(obuf[0]);
}

encode_base64()
{
	register int c;
	register int i;
	int j;
	char d[64];
	int buf[3];

	/* init encoding array */
	for(i='A'; i<='Z'; i++)
		d[i-'A'] = i;
	for(i='a'; i<='z'; i++)
		d[i-'G'] = i;
	for(i='0'; i<='9'; i++)
		d[i+4] = i;
	d[62] = '+';
	d[63] = '/';

	/* encode data */
	i = 0;
	for(;;) {
		c = getc(ibuf);
		if(c < 0)
			break;
		buf[i++] = c;
		if(i>=3) {
			putcw(d[buf[0]>>2], &j);
			putcw(d[((buf[0]&3)<<4) | ((buf[1]&0360)>>4)], &j);
			putcw(d[((buf[1]&017)<<2) | ((buf[2]&0300)>>6)], &j);
			putcw(d[buf[2]&077], &j);
			i = 0;
		}
	}
	if (i==1) {
		putcw(d[buf[0]>>2], &j);
		putcw(d[((buf[0]&3)<<4)], &j);
		putcw('=', &j);
		putcw('=', &j);
	} else if (i==2) {
		putcw(d[buf[0]>>2], &j);
		putcw(d[((buf[0]&3)<<4) | ((buf[1]&0360)>>4)], &j);
		putcw(d[((buf[1]&017)<<2)], &j);
		putcw('=', &j);
	}
	putc('\n', obuf);
}

putcw(ch,cnt)
char ch;
int *cnt;
{
    putc(ch, obuf);
    if(++(*cnt)>=wrap) {
	putc('\n', obuf);
	(*cnt) = 0;
    }
}

decode_base64()
{
	/* Based on: */
	/*   https://en.wikibooks.org/wiki/Algorithm_Implementation/Miscellaneous/Base64#C_2 */

	register int c;
	register int i;
	char buf[4];
	char d[256];

	/* init decoding array */
	for(i=0; i<=255; i++)
		d[i] = 100;
	for(i='A'; i<='Z'; i++)
		d[i] = i-'A';
	for(i='a'; i<='z'; i++)
		d[i] = i-'G';
	for(i='0'; i<='9'; i++)
		d[i] = i+4;
	d['+'] = 62;
	d['/'] = 63;
	d['='] = 126;
	d['\n'] = 77;

	/* decode input */
	i = 0;
	c = 0;
	while(c!=126) {
		c = getc(ibuf);
		if(c < 0)
			break;
		c = d[c];
		switch(c) {
		case 77:	/* newline */
			continue;
		case 100:	/* invalid */
			diag("error: invalid character, cannot decode\n");
			return;
		case 126:	/* equals */
			break;
		default:
			buf[i++] = c;
			if(i>=4) {
				putc((buf[0]<<2) | (buf[1]>>4), obuf);
				putc(((buf[1]&017)<<4) | (buf[2]>>2), obuf);
				putc(((buf[2]&3)<<6) | buf[3], obuf);
				i = 0;
			}
		}
	}
	if(i > 0) {
		putc((buf[0]<<2) | (buf[1]>>4), obuf);
		if(i == 3) {	/* two bytes left */
			putc(((buf[1]&017)<<4) | (buf[2]>>2), obuf);
		}
	}
}

diag(s)
char *s;
{
	while(*s)
		write(2,s++,1);
}
