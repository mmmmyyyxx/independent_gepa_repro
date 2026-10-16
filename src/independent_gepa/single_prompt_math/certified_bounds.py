"""Bounded exact interval separation; UNKNOWN always defers to the pinned grader."""
from fractions import Fraction
from math import isqrt


class UnknownBounds(Exception):pass


def definitely_separated(left,right,policy):
    """Return true only for a wide, exact separation of closed scalar values."""
    from sympy import Add,Mul,Pow,Rational,Float
    remaining=[policy['interval_max_nodes']]
    maximum=policy['interval_max_arithmetic_bits']
    def bounded(value):
        if max(abs(value.numerator).bit_length(),value.denominator.bit_length())>maximum:
            raise UnknownBounds()
        return value
    def multiply(a,b):
        if (abs(a.numerator).bit_length()+abs(b.numerator).bit_length()>maximum
            or a.denominator.bit_length()+b.denominator.bit_length()>maximum):
            raise UnknownBounds()
        return bounded(a*b)
    def square_root(value,upper):
        if value<0:raise UnknownBounds()
        bits=policy['interval_precision_bits'];scale=1<<bits
        if value.numerator.bit_length()+2*bits>maximum:raise UnknownBounds()
        floor=isqrt((value.numerator<<(2*bits))//value.denominator)
        return Fraction(floor+int(upper),scale)
    def interval(value):
        remaining[0]-=1
        if remaining[0]<0:raise UnknownBounds()
        if isinstance(value,Float):raise UnknownBounds()
        if isinstance(value,Rational):
            number=bounded(Fraction(int(value.p),int(value.q)));return number,number
        if isinstance(value,Add):
            lower=upper=Fraction(0)
            for item in value.args:
                lo,hi=interval(item);lower=bounded(lower+lo);upper=bounded(upper+hi)
            return lower,upper
        if isinstance(value,Mul):
            lower=upper=Fraction(1)
            for item in value.args:
                lo,hi=interval(item);products=[multiply(a,b) for a in (lower,upper) for b in (lo,hi)]
                lower,upper=min(products),max(products)
            return lower,upper
        if isinstance(value,Pow):
            base,exponent=value.args;lo,hi=interval(base)
            if exponent==Rational(1,2):return square_root(lo,False),square_root(hi,True)
            power=exact_integer(exponent)
            if abs(power)>policy['interval_max_finite_power']:raise UnknownBounds()
            if power<0:
                if lo<=0<=hi:raise UnknownBounds()
                lo,hi=Fraction(1,hi),Fraction(1,lo);power=-power
            lower=upper=Fraction(1)
            # The configured exponent limit bounds this loop and all rational sizes.
            for _ in range(power):
                products=[multiply(a,b) for a in (lower,upper) for b in (lo,hi)]
                lower,upper=min(products),max(products)
            return lower,upper
        raise UnknownBounds()
    def exact_integer(value):
        lo,hi=interval(value)
        if lo!=hi or lo.denominator!=1:raise UnknownBounds()
        return int(lo)
    def distant(lower,upper):
        margin=policy['separation_margin'];factor=policy['separation_factor']
        return lower>upper+margin and lower>factor*abs(upper)+margin
    def large_power_above(value,other):
        if not isinstance(value,Pow):return False
        base,exponent=value.args
        power=exact_integer(exponent)
        if power<=0:return False
        if power.bit_length()>policy['interval_max_exponent_bits']:return False
        lo,_=interval(base)
        if lo<=1:return False
        threshold=bounded(policy['separation_factor']*max(abs(other[0]),abs(other[1]))+policy['separation_margin'])
        cap=bounded(max(Fraction(2),threshold+1));factor=min(lo,cap);lower=Fraction(1)
        while power:
            if power&1:lower=min(multiply(lower,factor),cap)
            power>>=1
            if power:factor=min(multiply(factor,factor),cap)
            if lower>threshold:return True
        return False
    try:
        # A Float anywhere excludes the certificate, including inside a huge power.
        if left.has(Float) or right.has(Float):return False
        bounds=[]
        for expression in (left,right):
            try:bounds.append(interval(expression))
            except UnknownBounds:bounds.append(None)
        a,b=bounds
        if a is not None and b is not None:
            return distant(a[0],b[1]) or distant(b[0],a[1])
        if a is not None and large_power_above(right,a):return True
        if b is not None and large_power_above(left,b):return True
    except (UnknownBounds,ArithmeticError,ValueError,TypeError):pass
    return False
